import tensorflow as tf
from autokeras import CastToFloat32
from keras.models import load_model
from PIL import Image
import numpy as np
import requests
from io import BytesIO
import os

from .__refact import refact_image

model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '__model.h5')
model: tf.keras.Sequential = load_model(model_path, safe_mode=False)  # type: ignore


def get_image(url: str):
    """ (x, y, 3) """
    image = Image.open(BytesIO(requests.get(url).content))
    im_arr = np.asarray(image) / 255
    return im_arr


def str_image(img_arr):
    """ (16, 16) """
    img_str = str(img_arr).replace(" ", "").replace("[", "").replace("]", "").replace("0.", "##").replace("1.",
                                                                                                          "  ").replace(
        "##5", "--")
    return img_str


def get_answers(url: str, limit=7):
    im_arr = get_image(url)
    img_list = np.array(list(refact_image(im_arr, limit=limit)))[:, :, :, 0]
    preds = model.predict(img_list)
    sample = list("123456789ABDEFGHJLMNQRTYabdefghijmnqrty")
    glob_answer = []
    for values in preds:
        values = values
        pairs = zip(values, sample)
        sorted_pairs = sorted(pairs, key=lambda x: x[0], reverse=True)
        glob_answer.append(sorted_pairs[:2])
    answers: list[tuple[float, str]] = []
    for _ in range(2):
        answ: list[str] = []
        prob = 1
        less_prob = 1
        less_index = 0
        for index, pairs in enumerate(glob_answer):
            probality, letter = pairs[0]
            prob *= probality
            answ.append(letter)
            if probality < less_prob:
                less_prob = probality
                less_index = index
        answers.append((prob, ''.join(answ)))
        del glob_answer[less_index][0]
    print(answers)
    return answers
