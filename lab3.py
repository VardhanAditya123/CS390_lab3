  
import os
import numpy as np
import tensorflow as tf
from tensorflow import keras
import tensorflow.keras.backend as K
import random
from scipy.misc import imsave, imresize
from scipy.optimize import fmin_l_bfgs_b   # https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.fmin_l_bfgs_b.html
from tensorflow.keras.applications import vgg19
from tensorflow.keras.preprocessing.image import load_img, img_to_array, array_to_img
import warnings

random.seed(1618)
np.random.seed(1618)
tf.compat.v1.random.set_random_seed(1618)
tf.compat.v1.logging.set_verbosity( tf.compat.v1.logging.ERROR)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

CONTENT_IMG_PATH = "source.png"           #TODO: Add this.
STYLE_IMG_PATH = "style.png"             #TODO: Add this.
OUTPUT_IMG_PATH = "output.png"

CONTENT_IMG_H = 500
CONTENT_IMG_W = 500

STYLE_IMG_H = 500
STYLE_IMG_W = 500

CONTENT_WEIGHT = 100  # Alpha weight.
STYLE_WEIGHT = 1.0      # Beta weight.
TOTAL_WEIGHT = 1.0
img_nrows = 500
img_ncols = 500
IMAGE_HEIGHT = 500
IMAGE_WIDTH = 500
CHANNELS = 3
TRANSFER_ROUNDS = 10
numFilters = 20

#=============================<Helper Fuctions>=================================
'''
TODO: implement this.
This function should take the tensor and re-convert it to an image.
'''
def deprocess_image(x):
    # Util function to convert a tensor into a valid image
    x = x.reshape((CONTENT_IMG_H ,  CONTENT_IMG_W, 3))
    # Remove zero-center by mean pixel
    x[:, :, 0] += 103.939
    x[:, :, 1] += 116.779
    x[:, :, 2] += 123.68
    # 'BGR'->'RGB'
    x = x[:, :, ::-1]
    x = np.clip(x, 0, 255).astype("uint8")
    return x


def gramMatrix(x):
    features = K.batch_flatten(K.permute_dimensions(x, (2, 0, 1)))
    gram = K.dot(features, K.transpose(features))
    return gram



#========================<Loss Function Builder Functions>======================

def styleLoss(style, gen):
    return K.sum(K.square(gramMatrix(style) - gramMatrix(gen))) / (4 * (numFilters^2) *((CONTENT_IMG_W * CONTENT_IMG_H)^2))


def contentLoss(content, gen):
    return K.sum(K.square(gen - content))



def totalLoss(x):
    a = tf.square(
        x[:, : img_nrows - 1, : img_ncols - 1, :] - x[:, 1:, : img_ncols - 1, :]
    )
    b = tf.square(
        x[:, : img_nrows - 1, : img_ncols - 1, :] - x[:, : img_nrows - 1, 1:, :]
    )
    return tf.reduce_sum(tf.pow(a + b, 1.25))


#=========================<Pipeline Functions>==================================

def getRawData():
    print("   Loading images.")
    print("      Content image URL:  \"%s\"." % CONTENT_IMG_PATH)
    print("      Style image URL:    \"%s\"." % STYLE_IMG_PATH)
    cImg = load_img(CONTENT_IMG_PATH)
    tImg = cImg.copy()
    sImg = load_img(STYLE_IMG_PATH)
    print("      Images have been loaded.")
    return ((cImg, CONTENT_IMG_H, CONTENT_IMG_W), (sImg, STYLE_IMG_H, STYLE_IMG_W), (tImg, CONTENT_IMG_H, CONTENT_IMG_W))



def preprocessData(raw):
    img, ih, iw = raw
    img = img_to_array(img)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        img = imresize(img, (ih, iw, 3))
    img = img.astype("float64")
    img = np.expand_dims(img, axis=0)
    img = vgg19.preprocess_input(img)
    return img


'''
TODO: Allot of stuff needs to be implemented in this function.
First, make sure the model is set up properly.
Then construct the loss function (from content and style loss).
Gradient functions will also need to be created, or you can use K.Gradients().
Finally, do the style transfer with gradient descent.
Save the newly generated and deprocessed images.
'''
def styleTransfer(cData, sData, tData):
   
    print("   Building transfer model.")
    contentTensor = K.variable(cData)
    styleTensor = K.variable(sData)
    genTensor = K.placeholder((1, CONTENT_IMG_H, CONTENT_IMG_W, 3))
    inputTensor = K.concatenate([contentTensor, styleTensor, genTensor], axis=0)
    
    
    model = vgg19.VGG19(include_top =False, weights = "imagenet" , input_tensor = inputTensor)
   
    outputDict = dict([(layer.name, layer.output) for layer in model.layers])
    loss = tf.zeros(shape=())
    print("   VGG19 model loaded.")
    styleLayerNames = ["block1_conv1", "block2_conv1", "block3_conv1", "block4_conv1", "block5_conv1"]
    contentLayerName = "block5_conv2"
    print("   Calculating content loss.")
   
    contentLayer = outputDict[contentLayerName]
    contentOutput = contentLayer[0, :, :, :]
    genOutput = contentLayer[2, :, :, :]
    c_loss = 0
    s_loss = 0

    loss = loss + (CONTENT_WEIGHT)*contentLoss(contentOutput , genOutput)
    print("After Content:\n")
    print(loss)
    print("   Calculating style loss.")
   
    for layerName in styleLayerNames:
        styleLayer = outputDict[layerName]
        styleOutput = styleLayer[1, :, :, :]
        genOutput = styleLayer[2, :, :, :]
        loss = loss + (STYLE_WEIGHT / len(styleLayerNames))* styleLoss(styleOutput,genOutput) 
   
    loss += TOTAL_WEIGHT * totalLoss(genTensor)
    
   
    # TODO: Setup gradients or use K.gradients().

    print("   Beginning transfer.")
    x = tData

    # grads = K.gradients(loss, tData)
    # outputs = [loss]
    # outputs.append(grads)
    # kFunction = K.function([genTensor] , outputs)([x])

    outputs = [loss]
    outputs += K.gradients(loss, genTensor)

    def evaluate_loss_and_gradients(x):
        x = x.reshape((1, IMAGE_HEIGHT, IMAGE_WIDTH, CHANNELS))
        outs = K.function([genTensor], outputs)([x])
        loss = outs[0]
        gradients = outs[1].flatten().astype("float64")
        return loss, gradients

    class Evaluator:

        def loss(self, x):
            loss, gradients = evaluate_loss_and_gradients(x)
            self._gradients = gradients
            return loss

        def gradients(self, x):
            return self._gradients

    evaluator = Evaluator()
    for i in range(TRANSFER_ROUNDS):
        print("   Step %d." % i)
        # x, loss, info = fmin_l_bfgs_b( func=kFunction, x0=x.flatten(), fprime=grads , maxiter=20)
        tData, loss, info = fmin_l_bfgs_b(evaluator.loss, tData, fprime=evaluator.gradients, maxfun=20)
        print("   Loss: %f." % loss)
        img = deprocess_image(tData)
        img = array_to_img(img)
        saveFile = img.save( OUTPUT_IMG_PATH )   #TODO: Implement.
        # imsave(saveFile, img)   #Uncomment when everything is working right.
        print("      Image saved to \"%s\"." % saveFile)
        print("   Transfer complete.")
       





#=========================<Main>================================================

def main():
    print("Starting style transfer program.")
    raw = getRawData()
    cData = preprocessData(raw[0])   # Content image.
    sData = preprocessData(raw[1])   # Style image.
    tData = preprocessData(raw[2])   # Transfer image.
    styleTransfer(cData, sData, tData)
    print("Done. Goodbye.")



if __name__ == "__main__":
    main()