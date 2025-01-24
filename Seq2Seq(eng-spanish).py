# -*- coding: utf-8 -*-
"""Sequence2sequence.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1OtCUAro8l5TGEjJyY-dXTsEdOJseaJ7I
"""

!pip install -q --upgrade rouge-score
!pip install -q --upgrade keras-hub
!pip install -q --upgrade keras

!pip install --upgrade tf-keras

!pip install tensorflow==2.17

import keras
import pathlib
import random
import keras_hub
from keras import ops
import torch
import tensorflow.data as tf_data
from tensorflow_text.tools.wordpiece_vocab import (
    bert_vocab_from_dataset as bert_vocab,
)

#now lets define our parameters and the hyperparameters as well
BATCH_SIZE=64
EPOCHS=1 #This must be at least 10 for getting the convergence level
MAX_SEQUENCE_LENGTH=40
ENG_VOCAB_SIZE=15000
SPA_VOCAB_SIZE=15000
EMBED_DIM=256
INTERMEDIATE_DIM = 512
NUM_HEADS=8

#NEXT WE NEED TO DOWNLOAD THE DATA THAT WE AHVE
text_file=keras.utils.get_file(
    fname="spa-eng.zip",
    origin="http://storage.googleapis.com/download.tensorflow.org/data/spa-eng.zip",
    extract=True
)
text_file=pathlib.Path(text_file).parent/"spa-eng"/"spa.txt"

import pathlib

# Specify the path to the downloaded dataset in your local storage
local_path = "/path/to/your/dataset/spa-eng/spa.txt"  # Replace with your actual file path

# Create a pathlib Path object for easier file handling
text_file = pathlib.Path(local_path)



import pathlib

# Specify the path to the downloaded dataset in your local storage
local_path = "/spa.txt"  # Replace with your actual file path

# Create a pathlib Path object for easier file handling
text_file = pathlib.Path(local_path)

#next we need to parse the data
#so from the file each line contains the english sentence and the corresponding spanish senetence
#and the input is the english sequence and the target sequence is the spanish sentence
#so we need to do some kind of pre-processing first
with open(text_file) as f:
  lines=f.read().split("\n")[:-1]
text_pairs=[]
for line in lines:
  eng,spa=line.split("\t") #so the first word before the whitespace is consdiered as the eng adn the next word after the white space is conisdered as the spa word
  eng=eng.lower()
  spa=spa.lower()
  text_pairs.append((eng,spa))

#lets print what our sentence looks like
for _ in range(5):
  print(random.choice(text_pairs))

#now we need to splie the sentence into training and teset set
random.shuffle(text_pairs)
num_val_samples = int(0.15 * len(text_pairs))
num_train_samples = len(text_pairs) - 2 * num_val_samples
train_pairs = text_pairs[:num_train_samples]
val_pairs = text_pairs[num_train_samples : num_train_samples + num_val_samples]
test_pairs = text_pairs[num_train_samples + num_val_samples :]

print(f"{len(text_pairs)} total pairs")
print(f"{len(train_pairs)} training pairs")
print(f"{len(val_pairs)} validation pairs")
print(f"{len(test_pairs)} test pairs")

def train_word_piece(text_samples, vocab_size, reserved_tokens):
    word_piece_ds = tf_data.Dataset.from_tensor_slices(text_samples)
    vocab = keras_hub.tokenizers.compute_word_piece_vocabulary(
        word_piece_ds.batch(1000).prefetch(2),
        vocabulary_size=vocab_size,
        reserved_tokens=reserved_tokens,
    )
    return vocab

reserved_tokens = ["[PAD]", "[UNK]", "[START]", "[END]"]

eng_samples = [text_pair[0] for text_pair in train_pairs]
eng_vocab = train_word_piece(eng_samples, ENG_VOCAB_SIZE, reserved_tokens)

spa_samples = [text_pair[1] for text_pair in train_pairs]
spa_vocab = train_word_piece(spa_samples, SPA_VOCAB_SIZE, reserved_tokens)

print("English Tokens: ", eng_vocab[100:110])
print("Spanish Tokens: ", spa_vocab[100:110])

eng_tokenizer = keras_hub.tokenizers.WordPieceTokenizer(
    vocabulary=eng_vocab, lowercase=False
)
spa_tokenizer = keras_hub.tokenizers.WordPieceTokenizer(
    vocabulary=spa_vocab, lowercase=False
)

eng_input_ex = text_pairs[0][0]
eng_tokens_ex = eng_tokenizer.tokenize(eng_input_ex)
print("English sentence: ", eng_input_ex)
print("Tokens: ", eng_tokens_ex)
print(
    "Recovered text after detokenizing: ",
    eng_tokenizer.detokenize(eng_tokens_ex),
)

print()

spa_input_ex = text_pairs[0][1]
spa_tokens_ex = spa_tokenizer.tokenize(spa_input_ex)
print("Spanish sentence: ", spa_input_ex)
print("Tokens: ", spa_tokens_ex)
print(
    "Recovered text after detokenizing: ",
    spa_tokenizer.detokenize(spa_tokens_ex),)

def preprocess_batch(eng, spa):
    batch_size = ops.shape(spa)[0]

    eng = eng_tokenizer(eng)
    spa = spa_tokenizer(spa)

    # Pad `eng` to `MAX_SEQUENCE_LENGTH`.
    eng_start_end_packer = keras_hub.layers.StartEndPacker(
        sequence_length=MAX_SEQUENCE_LENGTH,
        pad_value=eng_tokenizer.token_to_id("[PAD]"),
    )
    eng = eng_start_end_packer(eng)

    # Add special tokens (`"[START]"` and `"[END]"`) to `spa` and pad it as well.
    spa_start_end_packer = keras_hub.layers.StartEndPacker(
        sequence_length=MAX_SEQUENCE_LENGTH + 1,
        start_value=spa_tokenizer.token_to_id("[START]"),
        end_value=spa_tokenizer.token_to_id("[END]"),
        pad_value=spa_tokenizer.token_to_id("[PAD]"),
    )
    spa = spa_start_end_packer(spa)

    return (
        {
            "encoder_inputs": eng,
            "decoder_inputs": spa[:, :-1],
        },
        spa[:, 1:],
    )


def make_dataset(pairs):
    eng_texts, spa_texts = zip(*pairs)
    eng_texts = list(eng_texts)
    spa_texts = list(spa_texts)
    dataset = tf_data.Dataset.from_tensor_slices((eng_texts, spa_texts))
    dataset = dataset.batch(BATCH_SIZE)
    dataset = dataset.map(preprocess_batch, num_parallel_calls=tf_data.AUTOTUNE)
    return dataset.shuffle(2048).prefetch(16).cache()


train_ds = make_dataset(train_pairs)
val_ds = make_dataset(val_pairs)

for inputs, targets in train_ds.take(1):
    print(f'inputs["encoder_inputs"].shape: {inputs["encoder_inputs"].shape}')
    print(f'inputs["decoder_inputs"].shape: {inputs["decoder_inputs"].shape}')
    print(f"targets.shape: {targets.shape}")

# Encoder
encoder_inputs = keras.Input(shape=(None,), name="encoder_inputs")

# Token and position embedding for the encoder
x = keras_hub.layers.TokenAndPositionEmbedding(
    vocabulary_size=ENG_VOCAB_SIZE,
    sequence_length=MAX_SEQUENCE_LENGTH,
    embedding_dim=EMBED_DIM,
)(encoder_inputs)

# Transformer encoder layer
encoder_outputs = keras_hub.layers.TransformerEncoder(
    intermediate_dim=INTERMEDIATE_DIM, num_heads=NUM_HEADS
)(inputs=x)

# Define the encoder model
encoder = keras.Model(encoder_inputs, encoder_outputs)

# Decoder
decoder_inputs = keras.Input(shape=(None,), name="decoder_inputs")
encoded_seq_inputs = keras.Input(shape=(None, EMBED_DIM), name="decoder_state_inputs")

# Token and position embedding for the decoder
x = keras_hub.layers.TokenAndPositionEmbedding(
    vocabulary_size=SPA_VOCAB_SIZE,
    sequence_length=MAX_SEQUENCE_LENGTH,
    embedding_dim=EMBED_DIM,
)(decoder_inputs)

# Transformer decoder layer
x = keras_hub.layers.TransformerDecoder(
    intermediate_dim=INTERMEDIATE_DIM, num_heads=NUM_HEADS
)(decoder_sequence=x, encoder_sequence=encoded_seq_inputs)

# Dropout and output layer for the decoder
x = keras.layers.Dropout(0.5)(x)
decoder_outputs = keras.layers.Dense(SPA_VOCAB_SIZE, activation="softmax")(x)

# Define the decoder model
decoder = keras.Model(
    [decoder_inputs, encoded_seq_inputs],
    decoder_outputs,
)

# Combine encoder and decoder
decoder_outputs = decoder([decoder_inputs, encoder_outputs])
transformer = keras.Model(
    [encoder_inputs, decoder_inputs],
    decoder_outputs,
    name="transformer",
)

transformer.summary()
transformer.compile(
    "rmsprop", loss="sparse_categorical_crossentropy", metrics=["accuracy"]
)
transformer.fit(train_ds, epochs=EPOCHS, validation_data=val_ds)

import tensorflow as tf
import random
from tensorflow.keras.preprocessing.sequence import pad_sequences

# Assuming `transformer`, `eng_tokenizer`, and `spa_tokenizer` are already defined

# Define constants
MAX_SEQUENCE_LENGTH = 40  # Example value, adjust as needed

def decode_sequences(input_sentences):
    batch_size = 1

    # Tokenize the encoder input
    encoder_input_tokens = eng_tokenizer(input_sentences)  # Assuming it returns sequences of token IDs

    # Pad sequences to match MAX_SEQUENCE_LENGTH
    encoder_input_tokens = pad_sequences(
        encoder_input_tokens, maxlen=MAX_SEQUENCE_LENGTH, padding='post', truncating='post'
    )
    encoder_input_tokens = tf.convert_to_tensor(encoder_input_tokens)  # Convert to TensorFlow tensor

    # Define a function that outputs the next token's probability given the input sequence
    def next(prompt, cache, index):
        logits = transformer([encoder_input_tokens, prompt])[:, index - 1, :]
        hidden_states = None  # Only needed for advanced sampling methods
        return logits, hidden_states, cache

    # Build a prompt of length 40 with a start token and padding tokens
    length = MAX_SEQUENCE_LENGTH
    start = tf.fill((batch_size, 1), spa_tokenizer.token_to_id("[START]"))
    pad = tf.fill((batch_size, length - 1), spa_tokenizer.token_to_id("[PAD]"))
    prompt = tf.concat((start, pad), axis=-1)

    # Use greedy sampling to generate the output sequence
   # Use greedy sampling to generate the output sequence
    generated_tokens = keras_hub.samplers.GreedySampler()(
       next,
       prompt,
       stop_token_ids=[spa_tokenizer.token_to_id("[END]")],
       index=1,  # Start sampling after the start token
)

    generated_sentences = spa_tokenizer.detokenize(generated_tokens)
    return generated_sentences

# Example test
test_eng_texts = [pair[0] for pair in test_pairs]  # Assuming `test_pairs` is defined
for i in range(2):
    input_sentence = random.choice(test_eng_texts)
    translated = decode_sequences([input_sentence])

    # Assuming `spa_tokenizer.detokenize()` returns a list of strings
    if isinstance(translated, list):
        translated = translated[0]  # Access the first (and only) item
    elif hasattr(translated, 'numpy'):  # If it's a TensorFlow tensor
        translated = translated.numpy()[0].decode("utf-8")
    else:
        raise TypeError(f"Unexpected type for translated: {type(translated)}")

    # Clean up special tokens
    translated = (
        translated.replace("[PAD]", "")
        .replace("[START]", "")
        .replace("[END]", "")
        .strip()
    )

    print(f"** Example {i} **")
    print("Input Sentence:", input_sentence)
    print("Translated Sentence:", translated)
    print()

rouge_1 = keras_hub.metrics.RougeN(order=1)
rouge_2 = keras_hub.metrics.RougeN(order=2)

for test_pair in test_pairs[:30]:
    input_sentence = test_pair[0]
    reference_sentence = test_pair[1]

    # Decode the input sentence
    translated_sentence = decode_sequences([input_sentence])

    # Ensure translated_sentence is properly handled
    if isinstance(translated_sentence, list):
        translated_sentence = translated_sentence[0]  # Use the first element if it's a list

    # Clean up special tokens
    translated_sentence = (
        translated_sentence.replace("[PAD]", "")
        .replace("[START]", "")
        .replace("[END]", "")
        .strip()
    )

    # Update metrics
    rouge_1(reference_sentence, translated_sentence)
    rouge_2(reference_sentence, translated_sentence)
# Display resultsrouge_1_result = rouge_1.result()
rouge_2_result = rouge_2.result()

# Convert TensorFlow tensors to Python floats
rouge_1_precision = rouge_1_result["precision"].numpy()
rouge_1_recall = rouge_1_result["recall"].numpy()
rouge_1_f1 = rouge_1_result["f1_score"].numpy()

rouge_2_precision = rouge_2_result["precision"].numpy()
rouge_2_recall = rouge_2_result["recall"].numpy()
rouge_2_f1 = rouge_2_result["f1_score"].numpy()

print(f"ROUGE-1 Precision: {rouge_1_precision:.3f}, Recall: {rouge_1_recall:.3f}, F1 Score: {rouge_1_f1:.3f}")
print(f"ROUGE-2 Precision: {rouge_2_precision:.3f}, Recall: {rouge_2_recall:.3f}, F1 Score: {rouge_2_f1:.3f}")
