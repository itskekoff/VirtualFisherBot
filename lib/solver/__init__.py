import sys
import os
import keras
import tensorflow as tf

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
keras.utils.disable_interactive_logging()
tf.get_logger().setLevel('ERROR')

from .__solver import get_answers

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
