import os
import numpy as np
import tensorflow as tf
import cv2
import csv

# Helpful Resources:
# https://stackoverflow.com/questions/49698567/how-to-save-tensorflow-model-using-estimator-export-savemodel/49805051
def serving_input_receiver_fn():
    serialized_tf_example = tf.placeholder(dtype=tf.string, name="input_tensors")
    receiver_tensors = {"predictor_inputs": serialized_tf_example}
    feature_spec = {'x': tf.FixedLenSequenceFeature(shape=[150, 150, 3], dtype=tf.float32, allow_missing=True)}
    test_features = tf.parse_example(serialized_tf_example, feature_spec)
    return tf.estimator.export.ServingInputReceiver(test_features, receiver_tensors)

def cnn_model_fn(features, labels, mode):
  """
  Model function for CNN.
  """
  features = features[list(features.keys())[0]]

  # NOTE: only uncomment and use this if saving entire file AFTER training
  # TODO: figure out proper way to do this
  print(features)
  features = tf.reshape(features, [-1, 150, 150, 3])
  print(features)

  # Feature Extractor:
  # ---------------------------------------------------------------------------------------------------------
  # Convolutional Layer #1
  # 15x15 kernel, 50 filters
  # Input: [batch_size, 150, 150, 3]
  # Output: [batch_size, 136, 136, 50]
  # https://www.quora.com/How-can-I-calculate-the-size-of-output-of-convolutional-layer
  conv1 = tf.layers.conv2d(
      inputs=features,
      filters=50,
      kernel_size=[15, 15],
      padding="valid",
      activation=tf.nn.relu)

  # Pooling Layer #1
  # 4x4 pool, stride size of 2
  # Input: [batch_size, 136, 136, 50]
  # Output: [batch_size, 67, 67, 50]
  # *see above ^
  pool1 = tf.layers.max_pooling2d(inputs=conv1, pool_size=[4, 4], strides=2)

  # Convolutional Layer #2
  # 5x5 kernel, 75 filters
  # Input: [batch_size, 67, 67, 50]
  # Output: [batch_size, 63, 63, 75]
  conv2 = tf.layers.conv2d(
      inputs=pool1,
      filters=75,
      kernel_size=[5, 5],
      padding="valid",
      activation=tf.nn.relu)

  # Pooling Layer #2
  # 3x3 pool, stride size of 2
  # Input: [batch_size, 63, 63, 75]
  # Output: [batch_size, 31, 31, 75]
  pool2 = tf.layers.max_pooling2d(inputs=conv2, pool_size=[3, 3], strides=2)

  # Convolutional Layer #3
  # 3x3 kernel, 100 filters
  # Input: [batch_size, 31, 31, 75]
  # Output: [batch_size, 29, 29, 100]
  conv3 = tf.layers.conv2d(
      inputs=pool2,
      filters=100,
      kernel_size=[3, 3],
      padding="valid",
      activation=tf.nn.relu)

  # Pooling Layer #3
  # 3x3 pool, stride size of 2
  # Input: [batch_size, 29, 29, 100]
  # Output: [batch_size, 14, 14, 100]
  pool3 = tf.layers.max_pooling2d(inputs=conv3, pool_size=[3, 3], strides=2)

  # Convolutional Layer #4
  # 3x3 kernel, 150 filters
  # Input: [batch_size, 14, 14, 100]
  # Output: [batch_size, 12, 12, 150]
  conv4 = tf.layers.conv2d(
      inputs=pool3,
      filters=150,
      kernel_size=[3, 3],
      padding="valid",
      activation=tf.nn.relu)

  # Pooling Layer #3
  # 2x2 pool, stride size of 2
  # Input: [batch_size, 12, 12, 150]
  # Output: [batch_size, 6, 6, 150]
  pool4 = tf.layers.max_pooling2d(inputs=conv4, pool_size=[2, 2], strides=2)

  # Determination:
  # ---------------------------------------------------------------------------------------------------------
  # Flatten tensor into a batch of vectors
  # Input Tensor Shape: [batch_size, 6, 6, 150]
  # Output Tensor Shape: [batch_size, 6 * 6 * 150]
  pool4_flat = tf.reshape(pool4, [-1, 6 * 6 * 150])

  # Dense Layer
  # Input Tensor Shape: [batch_size, 6 * 6 * 150]
  # Output Tensor Shape: [batch_size, 1024]
  dense = tf.layers.dense(inputs=pool4_flat, units=1024, activation=tf.nn.relu)

  # Add dropout operation; 0.6 probability that element will be kept
  dropout = tf.layers.dropout(
      inputs=dense, rate=0.4, training=mode == tf.estimator.ModeKeys.TRAIN)

  # Logits layer
  # Input Tensor Shape: [batch_size, 1024]
  # Output Tensor Shape: [batch_size, 2]
  logits = tf.layers.dense(inputs=dropout, units=2)

  # Results:
  # ---------------------------------------------------------------------------------------------------------
  predictions = {
      # Generate predictions (for PREDICT and EVAL mode)
      "classes": tf.argmax(input=logits, axis=1),
      # Add `softmax_tensor` to the graph. It is used for PREDICT and by the
      # `logging_hook`.
      "probabilities": tf.nn.softmax(logits, name="softmax_tensor")
  }
  if mode == tf.estimator.ModeKeys.PREDICT:
    export_outputs = {'predict_output': tf.estimator.export.PredictOutput(predictions)}
    return tf.estimator.EstimatorSpec(mode=mode, predictions=predictions, export_outputs=export_outputs)

  # Calculate Loss (for both TRAIN and EVAL modes)
  loss = tf.losses.sparse_softmax_cross_entropy(labels=labels, logits=logits)

  # Configure the Training Op (for TRAIN mode)
  if mode == tf.estimator.ModeKeys.TRAIN:
    print("features: ")
    print(type(features))
    print(features)
    print("labels: ")
    print(labels.dtype)
    print(labels.get_shape().as_list())
    print("logits layer: ")
    print(logits.dtype)
    print(logits.get_shape().as_list())
    print("loss layer: ")
    print(loss.dtype)
    print(loss.get_shape().as_list())

    # DEBUG
    #exit()

    optimizer = tf.train.GradientDescentOptimizer(learning_rate=0.0001)
    train_op = optimizer.minimize(
        loss=loss,
        global_step=tf.train.get_global_step())
    return tf.estimator.EstimatorSpec(mode=mode, loss=loss, train_op=train_op)

  # Add evaluation metrics (for EVAL mode)
  eval_metric_ops = {
      "accuracy": tf.metrics.accuracy(
          labels=labels, predictions=predictions["classes"])}
  return tf.estimator.EstimatorSpec(mode=mode, loss=loss, eval_metric_ops=eval_metric_ops)

def main(unused_argv):
  # Load training and testing data
  train_data = np.zeros(shape=(1000, 150, 150, 3))
  train_labels = np.zeros(shape=(1000))
  test_data = np.zeros(shape=(50, 150, 150, 3))
  test_labels = np.zeros(shape=(50))
  train_directory = "./temp_data/alex-training-data"
  train_labels_file = "./temp_data/train-labels.csv"
  test_directory = "./temp_data/alex-testing-data"
  test_labels_file = "./temp_data/test-labels.csv"
  for idx, img in enumerate(os.listdir(train_directory)):
      loaded_img = cv2.imread(train_directory + '/' + img)
      resized_img = cv2.resize(loaded_img, (150, 150))
      resized_img = (resized_img / (np.max(resized_img)/2)) - 1
      train_data[idx] = resized_img
  with open(train_labels_file, newline='') as csvfile:
      csvrdr = csv.reader(csvfile, delimiter=' ')
      for idx, r in enumerate(csvrdr):
          train_labels[idx] = int(r[0])

  for idx, img in enumerate(os.listdir(test_directory)):
      loaded_img = cv2.imread(test_directory + '/' + img)
      resized_img = cv2.resize(loaded_img, (150, 150))
      resized_img = (resized_img / (np.max(resized_img)/2)) - 1
      test_data[idx] = resized_img
  with open(test_labels_file, newline='') as csvfile:
      csvrdr = csv.reader(csvfile, delimiter=' ')
      for idx, r in enumerate(csvrdr):
          test_labels[idx] = int(r[0])
  train_data = train_data.astype(np.float32)
  train_labels = train_labels.astype(np.int32)
  test_data = test_data.astype(np.float32)
  test_labels = test_labels.astype(np.int32)

  assert not np.any(np.isnan(train_data))
  assert not np.any(np.isnan(train_labels))
  assert not np.any(np.isnan(test_data))
  assert not np.any(np.isnan(test_labels))

  #print(train_data.shape)
  #print(train_labels.shape)
  #print(test_data.shape)
  #print(test_labels.shape)

  # DEBUG
  #exit()

  # Create the Estimator
  tb_classifier = tf.estimator.Estimator(model_fn=cnn_model_fn, model_dir="./tb_cnn_model")

  # Set up logging for predictions, specifically "probabilities" from "softmax" tensor
  tensors_to_log = {"probabilities": "softmax_tensor"}
  logging_hook = tf.train.LoggingTensorHook(tensors=tensors_to_log, every_n_iter=50)

  # Train
  train_input_fn = tf.estimator.inputs.numpy_input_fn(
      x={"x": train_data},
      y=train_labels,
      batch_size=10,
      num_epochs=None,
      shuffle=True)
#  tb_classifier.train(
#      input_fn=train_input_fn,
#      steps=20000,
#      hooks=[logging_hook])

  # Test
  eval_input_fn = tf.estimator.inputs.numpy_input_fn(
      x={"x": test_data},
      y=test_labels,
      num_epochs=1,
      shuffle=False)

  # Results
  eval_results = tb_classifier.evaluate(input_fn=eval_input_fn)
  print(eval_results)

  # Export
  full_model_dir = tb_classifier.export_savedmodel(export_dir_base="./tb_cnn_model_serve", serving_input_receiver_fn=serving_input_receiver_fn)

if __name__ == "__main__":
  tf.app.run()
