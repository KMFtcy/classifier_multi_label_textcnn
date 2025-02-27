# -*- coding: utf-8 -*-
"""
Created on Wed Jul  8 20:03:12 2020

@author: cm
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import collections
import copy
import json
import math
import re
import numpy as np
import six
from six.moves import range
import tensorflow as tf
# from tensorflow.python.compiler.tensorrt import trt_convert as contrib_layers
from tensorflow.contrib import layers as contrib_layers


class AlbertConfig(object):
  """Configuration for `AlbertModel`.

  The default settings match the configuration of model `albert_xxlarge`.
  """

  def __init__(self,
               vocab_size,
               embedding_size=128,
               hidden_size=4096,
               num_hidden_layers=12,
               num_hidden_groups=1,
               num_attention_heads=64,
               intermediate_size=16384,
               inner_group_num=1,
               down_scale_factor=1,
               hidden_act="gelu",
               hidden_dropout_prob=0,
               attention_probs_dropout_prob=0,
               max_position_embeddings=512,
               type_vocab_size=2,
               initializer_range=0.02):
    """Constructs AlbertConfig.

    Args:
      vocab_size: Vocabulary size of `inputs_ids` in `AlbertModel`.
      embedding_size: size of voc embeddings.
      hidden_size: Size of the encoder layers and the pooler layer.
      num_hidden_layers: Number of hidden layers in the Transformer encoder.
      num_hidden_groups: Number of group for the hidden layers, parameters in
        the same group are shared.
      num_attention_heads: Number of attention heads for each attention layer in
        the Transformer encoder.
      intermediate_size: The size of the "intermediate" (i.e., feed-forward)
        layer in the Transformer encoder.
      inner_group_num: int, number of inner repetition of attention and ffn.
      down_scale_factor: float, the scale to apply
      hidden_act: The non-linear activation function (function or string) in the
        encoder and pooler.
      hidden_dropout_prob: The dropout probability for all fully connected
        layers in the embeddings, encoder, and pooler.
      attention_probs_dropout_prob: The dropout ratio for the attention
        probabilities.
      max_position_embeddings: The maximum sequence length that this model might
        ever be used with. Typically set this to something large just in case
        (e.g., 512 or 1024 or 2048).
      type_vocab_size: The vocabulary size of the `token_type_ids` passed into
        `AlbertModel`.
      initializer_range: The stdev of the truncated_normal_initializer for
        initializing all weight matrices.
    """
    self.vocab_size = vocab_size
    self.embedding_size = embedding_size
    self.hidden_size = hidden_size
    self.num_hidden_layers = num_hidden_layers
    self.num_hidden_groups = num_hidden_groups
    self.num_attention_heads = num_attention_heads
    self.inner_group_num = inner_group_num
    self.down_scale_factor = down_scale_factor
    self.hidden_act = hidden_act
    self.intermediate_size = intermediate_size
    self.hidden_dropout_prob = hidden_dropout_prob
    self.attention_probs_dropout_prob = attention_probs_dropout_prob
    self.max_position_embeddings = max_position_embeddings
    self.type_vocab_size = type_vocab_size
    self.initializer_range = initializer_range

  @classmethod
  def from_dict(cls, json_object):
    """Constructs a `AlbertConfig` from a Python dictionary of parameters."""
    config = AlbertConfig(vocab_size=None)
    for (key, value) in six.iteritems(json_object):
      config.__dict__[key] = value
    return config

  @classmethod
  def from_json_file(cls, json_file):
    """Constructs a `AlbertConfig` from a json file of parameters."""
    with tf.io.gfile.GFile(json_file, "r") as reader:
      text = reader.read()
    return cls.from_dict(json.loads(text))

  def to_dict(self):
    """Serializes this instance to a Python dictionary."""
    output = copy.deepcopy(self.__dict__)
    return output

  def to_json_string(self):
    """Serializes this instance to a JSON string."""
    return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


class AlbertModel(object):
  """BERT model ("Bidirectional Encoder Representations from Transformers").

  Example usage:

  ```python
  # Already been converted from strings into ids
  input_ids = tf.constant([[31, 51, 99], [15, 5, 0]])
  input_mask = tf.constant([[1, 1, 1], [1, 1, 0]])
  token_type_ids = tf.constant([[0, 0, 1], [0, 2, 0]])

  config = modeling.AlbertConfig(vocab_size=32000, hidden_size=512,
    num_hidden_layers=8, num_attention_heads=6, intermediate_size=1024)

  model = modeling.AlbertModel(config=config, is_training=True,
    input_ids=input_ids, input_mask=input_mask, token_type_ids=token_type_ids)

  label_embeddings = tf.get_variable(...)
  pooled_output = model.get_pooled_output()
  logits = tf.matmul(pooled_output, label_embeddings)
  ...
  ```
  """

  def __init__(self,
               config,
               is_training,
               input_ids,
               input_mask=None,
               token_type_ids=None,
               use_one_hot_embeddings=False,
               scope=None):
    """Constructor for AlbertModel.

    Args:
      config: `AlbertConfig` instance.
      is_training: bool. true for training model, false for eval model. Controls
        whether dropout will be applied.
      input_ids: int32 Tensor of shape [batch_size, seq_length].
      input_mask: (optional) int32 Tensor of shape [batch_size, seq_length].
      token_type_ids: (optional) int32 Tensor of shape [batch_size, seq_length].
      use_one_hot_embeddings: (optional) bool. Whether to use one-hot word
        embeddings or tf.embedding_lookup() for the word embeddings.
      scope: (optional) variable scope. Defaults to "bert".

    Raises:
      ValueError: The config is invalid or one of the input tensor shapes
        is invalid.
    """
    config = copy.deepcopy(config)
    if not is_training:
      config.hidden_dropout_prob = 0.0
      config.attention_probs_dropout_prob = 0.0

    input_shape = get_shape_list(input_ids, expected_rank=2)
    batch_size = input_shape[0]
    seq_length = input_shape[1]

    if input_mask is None:
      input_mask = tf.ones(shape=[batch_size, seq_length], dtype=tf.int32)

    if token_type_ids is None:
      token_type_ids = tf.zeros(shape=[batch_size, seq_length], dtype=tf.int32)

    with tf.variable_scope(scope, default_name="albert"):
      with tf.variable_scope("embeddings"):
        # Perform embedding lookup on the word ids.
        (self.word_embedding_output,
         self.output_embedding_table) = embedding_lookup(
            input_ids=input_ids,
            vocab_size=config.vocab_size,
            embedding_size=config.embedding_size,
            initializer_range=config.initializer_range,
            word_embedding_name="word_embeddings",
            use_one_hot_embeddings=use_one_hot_embeddings)

        # Add positional embeddings and token type embeddings, then layer
        # normalize and perform dropout.
        self.embedding_output = embedding_postprocessor(
            input_tensor=self.word_embedding_output,
            use_token_type=True,
            token_type_ids=token_type_ids,
            token_type_vocab_size=config.type_vocab_size,
            token_type_embedding_name="token_type_embeddings",
            use_position_embeddings=True,
            position_embedding_name="position_embeddings",
            initializer_range=config.initializer_range,
            max_position_embeddings=config.max_position_embeddings,
            dropout_prob=config.hidden_dropout_prob)

      with tf.variable_scope("encoder"):

        # Run the stacked transformer.
        # `sequence_output` shape = [batch_size, seq_length, hidden_size].
        self.all_encoder_layers = transformer_model(
            input_tensor=self.embedding_output,
            attention_mask=input_mask,
            hidden_size=config.hidden_size,
            num_hidden_layers=config.num_hidden_layers,
            num_hidden_groups=config.num_hidden_groups,
            num_attention_heads=config.num_attention_heads,
            intermediate_size=config.intermediate_size,
            inner_group_num=config.inner_group_num,
            intermediate_act_fn=get_activation(config.hidden_act),
            hidden_dropout_prob=config.hidden_dropout_prob,
            attention_probs_dropout_prob=config.attention_probs_dropout_prob,
            initializer_range=config.initializer_range,
            do_return_all_layers=True)

      self.sequence_output = self.all_encoder_layers[-1]
      # The "pooler" converts the encoded sequence tensor of shape
      # [batch_size, seq_length, hidden_size] to a tensor of shape
      # [batch_size, hidden_size]. This is necessary for segment-level
      # (or segment-pair-level) classification tasks where we need a fixed
      # dimensional representation of the segment.
      with tf.variable_scope("pooler"):
        # We "pool" the model by simply taking the hidden state corresponding
        # to the first token. We assume that this has been pre-trained
        first_token_tensor = tf.squeeze(self.sequence_output[:, 0:1, :], axis=1)
        self.pooled_output = tf.layers.dense(
            first_token_tensor,
            config.hidden_size,
            activation=tf.tanh,
            kernel_initializer=create_initializer(config.initializer_range))

  def get_pooled_output(self):
    return self.pooled_output

  def get_sequence_output(self):
    """Gets final hidden layer of encoder.

    Returns:
      float Tensor of shape [batch_size, seq_length, hidden_size] corresponding
      to the final hidden of the transformer encoder.
    """
    return self.sequence_output

  def get_all_encoder_layers(self):
    return self.all_encoder_layers

  def get_word_embedding_output(self):
    """Get output of the word(piece) embedding lookup.

    This is BEFORE positional embeddings and token type embeddings have been
    added.

    Returns:
      float Tensor of shape [batch_size, seq_length, hidden_size] corresponding
      to the output of the word(piece) embedding layer.
    """
    return self.word_embedding_output

  def get_embedding_output(self):
    """Gets output of the embedding lookup (i.e., input to the transformer).

    Returns:
      float Tensor of shape [batch_size, seq_length, hidden_size] corresponding
      to the output of the embedding layer, after summing the word
      embeddings with the positional embeddings and the token type embeddings,
      then performing layer normalization. This is the input to the transformer.
    """
    return self.embedding_output

  def get_embedding_table(self):
    return self.output_embedding_table


def gelu(x):
  """Gaussian Error Linear Unit.

  This is a smoother version of the RELU.
  Original paper: https://arxiv.org/abs/1606.08415
  Args:
    x: float Tensor to perform activation.

  Returns:
    `x` with the GELU activation applied.
  """
  cdf = 0.5 * (1.0 + tf.tanh(
      (np.sqrt(2 / np.pi) * (x + 0.044715 * tf.pow(x, 3)))))
  return x * cdf


def get_activation(activation_string):
  """Maps a string to a Python function, e.g., "relu" => `tf.nn.relu`.

  Args:
    activation_string: String name of the activation function.

  Returns:
    A Python function corresponding to the activation function. If
    `activation_string` is None, empty, or "linear", this will return None.
    If `activation_string` is not a string, it will return `activation_string`.

  Raises:
    ValueError: The `activation_string` does not correspond to a known
      activation.
  """

  # We assume that anything that"s not a string is already an activation
  # function, so we just return it.
  if not isinstance(activation_string, six.string_types):
    return activation_string

  if not activation_string:
    return None

  act = activation_string.lower()
  if act == "linear":
    return None
  elif act == "relu":
    return tf.nn.relu
  elif act == "gelu":
    return gelu
  elif act == "tanh":
    return tf.tanh
  else:
    raise ValueError("Unsupported activation: %s" % act)


def get_assignment_map_from_checkpoint(tvars, init_checkpoint, num_of_group=0):
  """Compute the union of the current variables and checkpoint variables."""
  assignment_map = {}
  initialized_variable_names = {}

  name_to_variable = collections.OrderedDict()
  for var in tvars:
    name = var.name
    m = re.match("^(.*):\\d+$", name)
    if m is not None:
      name = m.group(1)
    name_to_variable[name] = var
  init_vars = tf.train.list_variables(init_checkpoint)
  init_vars_name = [name for (name, _) in init_vars]

  if num_of_group > 0:
    assignment_map = []
    for gid in range(num_of_group):
      assignment_map.append(collections.OrderedDict())
  else:
    assignment_map = collections.OrderedDict()

  for name in name_to_variable:
    if name in init_vars_name:
      tvar_name = name
    elif (re.sub(r"/group_\d+/", "/group_0/",
                 six.ensure_str(name)) in init_vars_name and
          num_of_group > 1):
      tvar_name = re.sub(r"/group_\d+/", "/group_0/", six.ensure_str(name))
    elif (re.sub(r"/ffn_\d+/", "/ffn_1/", six.ensure_str(name))
          in init_vars_name and num_of_group > 1):
      tvar_name = re.sub(r"/ffn_\d+/", "/ffn_1/", six.ensure_str(name))
    elif (re.sub(r"/attention_\d+/", "/attention_1/", six.ensure_str(name))
          in init_vars_name and num_of_group > 1):
      tvar_name = re.sub(r"/attention_\d+/", "/attention_1/",
                         six.ensure_str(name))
    else:
      tf.logging.info("name %s does not get matched", name)
      continue
    tf.logging.info("name %s match to %s", name, tvar_name)
    if num_of_group > 0:
      group_matched = False
      for gid in range(1, num_of_group):
        if (("/group_" + str(gid) + "/" in name) or
            ("/ffn_" + str(gid) + "/" in name) or
            ("/attention_" + str(gid) + "/" in name)):
          group_matched = True
          tf.logging.info("%s belongs to %dth", name, gid)
          assignment_map[gid][tvar_name] = name
      if not group_matched:
        assignment_map[0][tvar_name] = name
    else:
      assignment_map[tvar_name] = name
    initialized_variable_names[name] = 1
    initialized_variable_names[six.ensure_str(name) + ":0"] = 1

  return (assignment_map, initialized_variable_names)


def dropout(input_tensor, dropout_prob):
  """Perform dropout.

  Args:
    input_tensor: float Tensor.
    dropout_prob: Python float. The probability of dropping out a value (NOT of
      *keeping* a dimension as in `tf.nn.dropout`).

  Returns:
    A version of `input_tensor` with dropout applied.
  """
  if dropout_prob is None or dropout_prob == 0.0:
    return input_tensor

  output = tf.nn.dropout(input_tensor, rate=dropout_prob)
  return output


def layer_norm(input_tensor, name=None):
  """Run layer normalization on the last dimension of the tensor."""
  return contrib_layers.layer_norm(
      inputs=input_tensor, begin_norm_axis=-1, begin_params_axis=-1, scope=name)


def layer_norm_and_dropout(input_tensor, dropout_prob, name=None):
  """Runs layer normalization followed by dropout."""
  output_tensor = layer_norm(input_tensor, name)
  output_tensor = dropout(output_tensor, dropout_prob)
  return output_tensor


def create_initializer(initializer_range=0.02):
  """Creates a `truncated_normal_initializer` with the given range."""
  return tf.truncated_normal_initializer(stddev=initializer_range)


def get_timing_signal_1d_given_position(channels,
                                        position,
                                        min_timescale=1.0,
                                        max_timescale=1.0e4):
  """Get sinusoids of diff frequencies, with timing position given.

  Adapted from add_timing_signal_1d_given_position in
  //third_party/py/tensor2tensor/layers/common_attention.py

  Args:
    channels: scalar, size of timing embeddings to create. The number of
        different timescales is equal to channels / 2.
    position: a Tensor with shape [batch, seq_len]
    min_timescale: a float
    max_timescale: a float

  Returns:
    a Tensor of timing signals [batch, seq_len, channels]
  """
  num_timescales = channels // 2
  log_timescale_increment = (
      math.log(float(max_timescale) / float(min_timescale)) /
      (tf.to_float(num_timescales) - 1))
  inv_timescales = min_timescale * tf.exp(
      tf.to_float(tf.range(num_timescales)) * -log_timescale_increment)
  scaled_time = (
      tf.expand_dims(tf.to_float(position), 2) * tf.expand_dims(
          tf.expand_dims(inv_timescales, 0), 0))
  signal = tf.concat([tf.sin(scaled_time), tf.cos(scaled_time)], axis=2)
  signal = tf.pad(signal, [[0, 0], [0, 0], [0, tf.mod(channels, 2)]])
  return signal


def embedding_lookup(input_ids,
                     vocab_size,
                     embedding_size=128,
                     initializer_range=0.02,
                     word_embedding_name="word_embeddings",
                     use_one_hot_embeddings=False):
  """Looks up words embeddings for id tensor.

  Args:
    input_ids: int32 Tensor of shape [batch_size, seq_length] containing word
      ids.
    vocab_size: int. Size of the embedding vocabulary.
    embedding_size: int. Width of the word embeddings.
    initializer_range: float. Embedding initialization range.
    word_embedding_name: string. Name of the embedding table.
    use_one_hot_embeddings: bool. If True, use one-hot method for word
      embeddings. If False, use `tf.nn.embedding_lookup()`.

  Returns:
    float Tensor of shape [batch_size, seq_length, embedding_size].
  """
  # This function assumes that the input is of shape [batch_size, seq_length,
  # num_inputs].
  #
  # If the input is a 2D tensor of shape [batch_size, seq_length], we
  # reshape to [batch_size, seq_length, 1].
  if input_ids.shape.ndims == 2:
    input_ids = tf.expand_dims(input_ids, axis=[-1])

  embedding_table = tf.get_variable(
      name=word_embedding_name,
      shape=[vocab_size, embedding_size],
      initializer=create_initializer(initializer_range))

  if use_one_hot_embeddings:
    flat_input_ids = tf.reshape(input_ids, [-1])
    one_hot_input_ids = tf.one_hot(flat_input_ids, depth=vocab_size)
    output = tf.matmul(one_hot_input_ids, embedding_table)
  else:
    output = tf.nn.embedding_lookup(embedding_table, input_ids)

  input_shape = get_shape_list(input_ids)

  output = tf.reshape(output,
                      input_shape[0:-1] + [input_shape[-1] * embedding_size])
  return (output, embedding_table)


def embedding_postprocessor(input_tensor,
                            use_token_type=False,
                            token_type_ids=None,
                            token_type_vocab_size=16,
                            token_type_embedding_name="token_type_embeddings",
                            use_position_embeddings=True,
                            position_embedding_name="position_embeddings",
                            initializer_range=0.02,
                            max_position_embeddings=512,
                            dropout_prob=0.1):
  """Performs various post-processing on a word embedding tensor.

  Args:
    input_tensor: float Tensor of shape [batch_size, seq_length,
      embedding_size].
    use_token_type: bool. Whether to add embeddings for `token_type_ids`.
    token_type_ids: (optional) int32 Tensor of shape [batch_size, seq_length].
      Must be specified if `use_token_type` is True.
    token_type_vocab_size: int. The vocabulary size of `token_type_ids`.
    token_type_embedding_name: string. The name of the embedding table variable
      for token type ids.
    use_position_embeddings: bool. Whether to add position embeddings for the
      position of each token in the sequence.
    position_embedding_name: string. The name of the embedding table variable
      for positional embeddings.
    initializer_range: float. Range of the weight initialization.
    max_position_embeddings: int. Maximum sequence length that might ever be
      used with this model. This can be longer than the sequence length of
      input_tensor, but cannot be shorter.
    dropout_prob: float. Dropout probability applied to the final output tensor.

  Returns:
    float tensor with same shape as `input_tensor`.

  Raises:
    ValueError: One of the tensor shapes or input values is invalid.
  """
  input_shape = get_shape_list(input_tensor, expected_rank=3)
  batch_size = input_shape[0]
  seq_length = input_shape[1]
  width = input_shape[2]

  output = input_tensor

  if use_token_type:
    if token_type_ids is None:
      raise ValueError("`token_type_ids` must be specified if"
                       "`use_token_type` is True.")
    token_type_table = tf.get_variable(
        name=token_type_embedding_name,
        shape=[token_type_vocab_size, width],
        initializer=create_initializer(initializer_range))
    # This vocab will be small so we always do one-hot here, since it is always
    # faster for a small vocabulary.
    flat_token_type_ids = tf.reshape(token_type_ids, [-1])
    one_hot_ids = tf.one_hot(flat_token_type_ids, depth=token_type_vocab_size)
    token_type_embeddings = tf.matmul(one_hot_ids, token_type_table)
    token_type_embeddings = tf.reshape(token_type_embeddings,
                                       [batch_size, seq_length, width])
    output += token_type_embeddings

  if use_position_embeddings:
    assert_op = tf.assert_less_equal(seq_length, max_position_embeddings)
    with tf.control_dependencies([assert_op]):
      full_position_embeddings = tf.get_variable(
          name=position_embedding_name,
          shape=[max_position_embeddings, width],
          initializer=create_initializer(initializer_range))
      # Since the position embedding table is a learned variable, we create it
      # using a (long) sequence length `max_position_embeddings`. The actual
      # sequence length might be shorter than this, for faster training of
      # tasks that do not have long sequences.
      #
      # So `full_position_embeddings` is effectively an embedding table
      # for position [0, 1, 2, ..., max_position_embeddings-1], and the current
      # sequence has positions [0, 1, 2, ... seq_length-1], so we can just
      # perform a slice.
      position_embeddings = tf.slice(full_position_embeddings, [0, 0],
                                     [seq_length, -1])
      num_dims = len(output.shape.as_list())

      # Only the last two dimensions are relevant (`seq_length` and `width`), so
      # we broadcast among the first dimensions, which is typically just
      # the batch size.
      position_broadcast_shape = []
      for _ in range(num_dims - 2):
        position_broadcast_shape.append(1)
      position_broadcast_shape.extend([seq_length, width])
      position_embeddings = tf.reshape(position_embeddings,
                                       position_broadcast_shape)
      output += position_embeddings

  output = layer_norm_and_dropout(output, dropout_prob)
  return output


def dense_layer_3d(input_tensor,
                   num_attention_heads,
                   head_size,
                   initializer,
                   activation,
                   name=None):
  """A dense layer with 3D kernel.

  Args:
    input_tensor: float Tensor of shape [batch, seq_length, hidden_size].
    num_attention_heads: Number of attention heads.
    head_size: The size per attention head.
    initializer: Kernel initializer.
    activation: Actication function.
    name: The name scope of this layer.

  Returns:
    float logits Tensor.
  """

  input_shape = get_shape_list(input_tensor)
  hidden_size = input_shape[2]

  with tf.variable_scope(name):
    w = tf.get_variable(
        name="kernel",
        shape=[hidden_size, num_attention_heads * head_size],
        initializer=initializer)
    w = tf.reshape(w, [hidden_size, num_attention_heads, head_size])
    b = tf.get_variable(
        name="bias",
        shape=[num_attention_heads * head_size],
        initializer=tf.zeros_initializer)
    b = tf.reshape(b, [num_attention_heads, head_size])
    ret = tf.einsum("BFH,HND->BFND", input_tensor, w)
    ret += b
  if activation is not None:
    return activation(ret)
  else:
    return ret


def dense_layer_3d_proj(input_tensor,
                        hidden_size,
                        head_size,
                        initializer,
                        activation,
                        name=None):
  """A dense layer with 3D kernel for projection.

  Args:
    input_tensor: float Tensor of shape [batch,from_seq_length,
      num_attention_heads, size_per_head].
    hidden_size: The size of hidden layer.
    num_attention_heads: The size of output dimension.
    head_size: The size of head.
    initializer: Kernel initializer.
    activation: Actication function.
    name: The name scope of this layer.

  Returns:
    float logits Tensor.
  """
  input_shape = get_shape_list(input_tensor)
  num_attention_heads= input_shape[2]
  with tf.variable_scope(name):
    w = tf.get_variable(
        name="kernel",
        shape=[num_attention_heads * head_size, hidden_size],
        initializer=initializer)
    w = tf.reshape(w, [num_attention_heads, head_size, hidden_size])
    b = tf.get_variable(
        name="bias", shape=[hidden_size], initializer=tf.zeros_initializer)
    ret = tf.einsum("BFND,NDH->BFH", input_tensor, w)
    ret += b
  if activation is not None:
    return activation(ret)
  else:
    return ret


def dense_layer_2d(input_tensor,
                   output_size,
                   initializer,
                   activation,
                   num_attention_heads=1,
                   name=None):
  """A dense layer with 2D kernel.

  Args:
    input_tensor: Float tensor with rank 3.
    output_size: The size of output dimension.
    initializer: Kernel initializer.
    activation: Activation function.
    num_attention_heads: number of attention head in attention layer.
    name: The name scope of this layer.

  Returns:
    float logits Tensor.
  """
  del num_attention_heads  # unused
  input_shape = get_shape_list(input_tensor)
  hidden_size = input_shape[2]
  with tf.variable_scope(name):
    w = tf.get_variable(
        name="kernel",
        shape=[hidden_size, output_size],
        initializer=initializer)
    b = tf.get_variable(
        name="bias", shape=[output_size], initializer=tf.zeros_initializer)
    ret = tf.einsum("BFH,HO->BFO", input_tensor, w)
    ret += b
  if activation is not None:
    return activation(ret)
  else:
    return ret


def dot_product_attention(q, k, v, bias, dropout_rate=0.0):
  """Dot-product attention.

  Args:
    q: Tensor with shape [..., length_q, depth_k].
    k: Tensor with shape [..., length_kv, depth_k]. Leading dimensions must
      match with q.
    v: Tensor with shape [..., length_kv, depth_v] Leading dimensions must
      match with q.
    bias: bias Tensor (see attention_bias())
    dropout_rate: a float.

  Returns:
    Tensor with shape [..., length_q, depth_v].
  """
  logits = tf.matmul(q, k, transpose_b=True)  # [..., length_q, length_kv]
  logits = tf.multiply(logits, 1.0 / math.sqrt(float(get_shape_list(q)[-1])))
  if bias is not None:
    # `attention_mask` = [B, T]
    from_shape = get_shape_list(q)
    if len(from_shape) == 4:
      broadcast_ones = tf.ones([from_shape[0], 1, from_shape[2], 1], tf.float32)
    elif len(from_shape) == 5:
      # from_shape = [B, N, Block_num, block_size, depth]#
      broadcast_ones = tf.ones([from_shape[0], 1, from_shape[2], from_shape[3],
                                1], tf.float32)

    bias = tf.matmul(broadcast_ones,
                     tf.cast(bias, tf.float32), transpose_b=True)

    # Since attention_mask is 1.0 for positions we want to attend and 0.0 for
    # masked positions, this operation will create a tensor which is 0.0 for
    # positions we want to attend and -10000.0 for masked positions.
    adder = (1.0 - bias) * -10000.0

    # Since we are adding it to the raw scores before the softmax, this is
    # effectively the same as removing these entirely.
    logits += adder
  else:
    adder = 0.0

  attention_probs = tf.nn.softmax(logits, name="attention_probs")
  attention_probs = dropout(attention_probs, dropout_rate)
  return tf.matmul(attention_probs, v)


def attention_layer(from_tensor,
                    to_tensor,
                    attention_mask=None,
                    num_attention_heads=1,
                    query_act=None,
                    key_act=None,
                    value_act=None,
                    attention_probs_dropout_prob=0.0,
                    initializer_range=0.02,
                    batch_size=None,
                    from_seq_length=None,
                    to_seq_length=None):
  """Performs multi-headed attention from `from_tensor` to `to_tensor`.

  Args:
    from_tensor: float Tensor of shape [batch_size, from_seq_length,
      from_width].
    to_tensor: float Tensor of shape [batch_size, to_seq_length, to_width].
    attention_mask: (optional) int32 Tensor of shape [batch_size,
      from_seq_length, to_seq_length]. The values should be 1 or 0. The
      attention scores will effectively be set to -infinity for any positions in
      the mask that are 0, and will be unchanged for positions that are 1.
    num_attention_heads: int. Number of attention heads.
    query_act: (optional) Activation function for the query transform.
    key_act: (optional) Activation function for the key transform.
    value_act: (optional) Activation function for the value transform.
    attention_probs_dropout_prob: (optional) float. Dropout probability of the
      attention probabilities.
    initializer_range: float. Range of the weight initializer.
    batch_size: (Optional) int. If the input is 2D, this might be the batch size
      of the 3D version of the `from_tensor` and `to_tensor`.
    from_seq_length: (Optional) If the input is 2D, this might be the seq length
      of the 3D version of the `from_tensor`.
    to_seq_length: (Optional) If the input is 2D, this might be the seq length
      of the 3D version of the `to_tensor`.

  Returns:
    float Tensor of shape [batch_size, from_seq_length, num_attention_heads,
      size_per_head].

  Raises:
    ValueError: Any of the arguments or tensor shapes are invalid.
  """
  from_shape = get_shape_list(from_tensor, expected_rank=[2, 3])
  to_shape = get_shape_list(to_tensor, expected_rank=[2, 3])
  size_per_head = int(from_shape[2]/num_attention_heads)

  if len(from_shape) != len(to_shape):
    raise ValueError(
        "The rank of `from_tensor` must match the rank of `to_tensor`.")

  if len(from_shape) == 3:
    batch_size = from_shape[0]
    from_seq_length = from_shape[1]
    to_seq_length = to_shape[1]
  elif len(from_shape) == 2:
    if (batch_size is None or from_seq_length is None or to_seq_length is None):
      raise ValueError(
          "When passing in rank 2 tensors to attention_layer, the values "
          "for `batch_size`, `from_seq_length`, and `to_seq_length` "
          "must all be specified.")

  # Scalar dimensions referenced here:
  #   B = batch size (number of sequences)
  #   F = `from_tensor` sequence length
  #   T = `to_tensor` sequence length
  #   N = `num_attention_heads`
  #   H = `size_per_head`

  # `query_layer` = [B, F, N, H]
  q = dense_layer_3d(from_tensor, num_attention_heads, size_per_head,
                     create_initializer(initializer_range), query_act, "query")

  # `key_layer` = [B, T, N, H]
  k = dense_layer_3d(to_tensor, num_attention_heads, size_per_head,
                     create_initializer(initializer_range), key_act, "key")
  # `value_layer` = [B, T, N, H]
  v = dense_layer_3d(to_tensor, num_attention_heads, size_per_head,
                     create_initializer(initializer_range), value_act, "value")
  q = tf.transpose(q, [0, 2, 1, 3])
  k = tf.transpose(k, [0, 2, 1, 3])
  v = tf.transpose(v, [0, 2, 1, 3])
  if attention_mask is not None:
    attention_mask = tf.reshape(
        attention_mask, [batch_size, 1, to_seq_length, 1])
    # 'new_embeddings = [B, N, F, H]'
  new_embeddings = dot_product_attention(q, k, v, attention_mask,
                                         attention_probs_dropout_prob)

  return tf.transpose(new_embeddings, [0, 2, 1, 3])


def attention_ffn_block(layer_input,
                        hidden_size=768,
                        attention_mask=None,
                        num_attention_heads=1,
                        attention_head_size=64,
                        attention_probs_dropout_prob=0.0,
                        intermediate_size=3072,
                        intermediate_act_fn=None,
                        initializer_range=0.02,
                        hidden_dropout_prob=0.0):
  """A network with attention-ffn as sub-block.

  Args:
    layer_input: float Tensor of shape [batch_size, from_seq_length,
      from_width].
    hidden_size: (optional) int, size of hidden layer.
    attention_mask: (optional) int32 Tensor of shape [batch_size,
      from_seq_length, to_seq_length]. The values should be 1 or 0. The
      attention scores will effectively be set to -infinity for any positions in
      the mask that are 0, and will be unchanged for positions that are 1.
    num_attention_heads: int. Number of attention heads.
    attention_head_size: int. Size of attention head.
    attention_probs_dropout_prob: float. dropout probability for attention_layer
    intermediate_size: int. Size of intermediate hidden layer.
    intermediate_act_fn: (optional) Activation function for the intermediate
      layer.
    initializer_range: float. Range of the weight initializer.
    hidden_dropout_prob: (optional) float. Dropout probability of the hidden
      layer.

  Returns:
    layer output
  """

  with tf.variable_scope("attention_1"):
    with tf.variable_scope("self"):
      attention_output = attention_layer(
          from_tensor=layer_input,
          to_tensor=layer_input,
          attention_mask=attention_mask,
          num_attention_heads=num_attention_heads,
          attention_probs_dropout_prob=attention_probs_dropout_prob,
          initializer_range=initializer_range)

    # Run a linear projection of `hidden_size` then add a residual
    # with `layer_input`.
    with tf.variable_scope("output"):
      attention_output = dense_layer_3d_proj(
          attention_output,
          hidden_size,
          attention_head_size,
          create_initializer(initializer_range),
          None,
          name="dense")
      attention_output = dropout(attention_output, hidden_dropout_prob)
  attention_output = layer_norm(attention_output + layer_input)
  with tf.variable_scope("ffn_1"):
    with tf.variable_scope("intermediate"):
      intermediate_output = dense_layer_2d(
          attention_output,
          intermediate_size,
          create_initializer(initializer_range),
          intermediate_act_fn,
          num_attention_heads=num_attention_heads,
          name="dense")
      with tf.variable_scope("output"):
        ffn_output = dense_layer_2d(
            intermediate_output,
            hidden_size,
            create_initializer(initializer_range),
            None,
            num_attention_heads=num_attention_heads,
            name="dense")
      ffn_output = dropout(ffn_output, hidden_dropout_prob)
  ffn_output = layer_norm(ffn_output + attention_output)
  return ffn_output


def transformer_model(input_tensor,
                      attention_mask=None,
                      hidden_size=768,
                      num_hidden_layers=12,
                      num_hidden_groups=12,
                      num_attention_heads=12,
                      intermediate_size=3072,
                      inner_group_num=1,
                      intermediate_act_fn="gelu",
                      hidden_dropout_prob=0.1,
                      attention_probs_dropout_prob=0.1,
                      initializer_range=0.02,
                      do_return_all_layers=False):
  """Multi-headed, multi-layer Transformer from "Attention is All You Need".

  This is almost an exact implementation of the original Transformer encoder.

  See the original paper:
  https://arxiv.org/abs/1706.03762

  Also see:
  https://github.com/tensorflow/tensor2tensor/blob/master/tensor2tensor/models/transformer.py

  Args:
    input_tensor: float Tensor of shape [batch_size, seq_length, hidden_size].
    attention_mask: (optional) int32 Tensor of shape [batch_size, seq_length,
      seq_length], with 1 for positions that can be attended to and 0 in
      positions that should not be.
    hidden_size: int. Hidden size of the Transformer.
    num_hidden_layers: int. Number of layers (blocks) in the Transformer.
    num_hidden_groups: int. Number of group for the hidden layers, parameters
      in the same group are shared.
    num_attention_heads: int. Number of attention heads in the Transformer.
    intermediate_size: int. The size of the "intermediate" (a.k.a., feed
      forward) layer.
    inner_group_num: int, number of inner repetition of attention and ffn.
    intermediate_act_fn: function. The non-linear activation function to apply
      to the output of the intermediate/feed-forward layer.
    hidden_dropout_prob: float. Dropout probability for the hidden layers.
    attention_probs_dropout_prob: float. Dropout probability of the attention
      probabilities.
    initializer_range: float. Range of the initializer (stddev of truncated
      normal).
    do_return_all_layers: Whether to also return all layers or just the final
      layer.

  Returns:
    float Tensor of shape [batch_size, seq_length, hidden_size], the final
    hidden layer of the Transformer.

  Raises:
    ValueError: A Tensor shape or parameter is invalid.
  """
  if hidden_size % num_attention_heads != 0:
    raise ValueError(
        "The hidden size (%d) is not a multiple of the number of attention "
        "heads (%d)" % (hidden_size, num_attention_heads))

  attention_head_size = hidden_size // num_attention_heads
  input_shape = get_shape_list(input_tensor, expected_rank=3)
  input_width = input_shape[2]

  all_layer_outputs = []
  if input_width != hidden_size:
    prev_output = dense_layer_2d(
        input_tensor, hidden_size, create_initializer(initializer_range),
        None, name="embedding_hidden_mapping_in")
  else:
    prev_output = input_tensor
  with tf.variable_scope("transformer", reuse=tf.AUTO_REUSE):
    for layer_idx in range(num_hidden_layers):
      group_idx = int(layer_idx / num_hidden_layers * num_hidden_groups)
      with tf.variable_scope("group_%d" % group_idx):
        with tf.name_scope("layer_%d" % layer_idx):
          layer_output = prev_output
          for inner_group_idx in range(inner_group_num):
            with tf.variable_scope("inner_group_%d" % inner_group_idx):
              layer_output = attention_ffn_block(
                  layer_output, hidden_size, attention_mask,
                  num_attention_heads, attention_head_size,
                  attention_probs_dropout_prob, intermediate_size,
                  intermediate_act_fn, initializer_range, hidden_dropout_prob)
              prev_output = layer_output
              all_layer_outputs.append(layer_output)
  if do_return_all_layers:
    return all_layer_outputs
  else:
    return all_layer_outputs[-1]


def get_shape_list(tensor, expected_rank=None, name=None):
  """Returns a list of the shape of tensor, preferring static dimensions.

  Args:
    tensor: A tf.Tensor object to find the shape of.
    expected_rank: (optional) int. The expected rank of `tensor`. If this is
      specified and the `tensor` has a different rank, and exception will be
      thrown.
    name: Optional name of the tensor for the error message.

  Returns:
    A list of dimensions of the shape of tensor. All static dimensions will
    be returned as python integers, and dynamic dimensions will be returned
    as tf.Tensor scalars.
  """
  if name is None:
    name = tensor.name

  if expected_rank is not None:
    assert_rank(tensor, expected_rank, name)

  shape = tensor.shape.as_list()

  non_static_indexes = []
  for (index, dim) in enumerate(shape):
    if dim is None:
      non_static_indexes.append(index)

  if not non_static_indexes:
    return shape

  dyn_shape = tf.shape(tensor)
  for index in non_static_indexes:
    shape[index] = dyn_shape[index]
  return shape


def reshape_to_matrix(input_tensor):
  """Reshapes a >= rank 2 tensor to a rank 2 tensor (i.e., a matrix)."""
  ndims = input_tensor.shape.ndims
  if ndims < 2:
    raise ValueError("Input tensor must have at least rank 2. Shape = %s" %
                     (input_tensor.shape))
  if ndims == 2:
    return input_tensor

  width = input_tensor.shape[-1]
  output_tensor = tf.reshape(input_tensor, [-1, width])
  return output_tensor


def reshape_from_matrix(output_tensor, orig_shape_list):
  """Reshapes a rank 2 tensor back to its original rank >= 2 tensor."""
  if len(orig_shape_list) == 2:
    return output_tensor

  output_shape = get_shape_list(output_tensor)

  orig_dims = orig_shape_list[0:-1]
  width = output_shape[-1]

  return tf.reshape(output_tensor, orig_dims + [width])


def assert_rank(tensor, expected_rank, name=None):
  """Raises an exception if the tensor rank is not of the expected rank.

  Args:
    tensor: A tf.Tensor to check the rank of.
    expected_rank: Python integer or list of integers, expected rank.
    name: Optional name of the tensor for the error message.

  Raises:
    ValueError: If the expected shape doesn't match the actual shape.
  """
  if name is None:
    name = tensor.name

  expected_rank_dict = {}
  if isinstance(expected_rank, six.integer_types):
    expected_rank_dict[expected_rank] = True
  else:
    for x in expected_rank:
      expected_rank_dict[x] = True

  actual_rank = tensor.shape.ndims
  if actual_rank not in expected_rank_dict:
    scope_name = tf.get_variable_scope().name
    raise ValueError(
        "For the tensor `%s` in scope `%s`, the actual rank "
        "`%d` (shape = %s) is not equal to the expected rank `%s`" %
        (name, scope_name, actual_rank, str(tensor.shape), str(expected_rank)))
