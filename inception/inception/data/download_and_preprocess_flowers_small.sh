#!/bin/bash
# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

# Script to download and preprocess the flowers data set. This data set
# provides a demonstration for how to perform fine-tuning (i.e. tranfer
# learning) from one model to a new data set.
#
# This script provides a demonstration for how to prepare an arbitrary
# data set for training an Inception v3 model.
#
# We demonstrate this with the flowers data set which consists of images
# of labeled flower images from 5 classes:
#
# daisy, dandelion, roses, sunflowers, tulips
#
# The final output of this script are sharded TFRecord files containing
# serialized Example protocol buffers. See build_image_data.py for
# details of how the Example protocol buffer contains image data.
#
# Run this from the inception directory.
# E.G:  ~/Desktop/School/Fall2016/Research/DistributedSGD/models/inception
#
# usage:
#  sh inception/data/download_and_preprocess_flowers_mac.sh ./data/
set -e

if [ -z "$1" ]; then
  echo "usage download_and_preprocess_flowers.sh [data dir]"
  exit
fi

# Create the output and temporary directories.
DATA_DIR="${1%/}"
SCRATCH_DIR="${DATA_DIR}/raw-data/"
mkdir -p "${DATA_DIR}"
mkdir -p "${SCRATCH_DIR}"
WORK_DIR="./inception/data"

# Download the flowers data.
DATA_URL="http://download.tensorflow.org/example_images/flower_photos.tgz"
CURRENT_DIR=$(pwd)
cd "${DATA_DIR}"
TARBALL="flower_photos.tgz"
if [ ! -f ${TARBALL} ]; then
  echo "Downloading flower data set."
  wget -O ${TARBALL} "${DATA_URL}"
else
  echo "Skipping download of flower data."
fi

# Note the locations of the train and validation data.
TRAIN_DIRECTORY="${SCRATCH_DIR}train/"
VALIDATION_DIRECTORY="${SCRATCH_DIR}validation/"

# Expands the data into the flower_photos/ directory and rename it as the
# train directory.
tar xf flower_photos.tgz
cd ..
rm -rf "${TRAIN_DIRECTORY}" "${VALIDATION_DIRECTORY}"
mkdir -p "${TRAIN_DIRECTORY}"
mkdir -p "${VALIDATION_DIRECTORY}"
mv "${DATA_DIR}/flower_photos" "${TRAIN_DIRECTORY}"

# Train directory contains flower_photos/daisy, flower_photos/sunflowers...
#  Move everything 1 dir up.
cd "${TRAIN_DIRECTORY}/flower_photos"
cp -rf . ..
cd ..
rm -rf flower_photos
cd "${CURRENT_DIR}"

# Generate a list of 5 labels: daisy, dandelion, roses, sunflowers, tulips
LABELS_FILE="${SCRATCH_DIR}/labels.txt"
ls -1 "${TRAIN_DIRECTORY}" | grep -v 'LICENSE' | sed 's/\///' | sort > "${LABELS_FILE}"

# Delete all but 50 images in each category
while read LABEL; do
  TRAIN_DIR_FOR_LABEL="${TRAIN_DIRECTORY}/${LABEL}"

  N_IMAGES=$(ls -1 "${TRAIN_DIR_FOR_LABEL}" | wc -l)
  TO_DELETE_IMAGES=$(ls -1 "${TRAIN_DIR_FOR_LABEL}" | gshuf | head -n $((N_IMAGES-30)))
  for IMAGE in ${TO_DELETE_IMAGES}; do
    rm -f "${TRAIN_DIR_FOR_LABEL}/${IMAGE}"
  done
done < "${LABELS_FILE}"

# Generate the validation data set.
while read LABEL; do
  VALIDATION_DIR_FOR_LABEL="${VALIDATION_DIRECTORY}${LABEL}"
  TRAIN_DIR_FOR_LABEL="${TRAIN_DIRECTORY}/${LABEL}"

  echo "${VALIDATION_DIR_FOR_LABEL}"
  echo "${TRAIN_DIR_FOR_LABEL}"

  # Move the first randomly selected 10 images to the validation set.
  mkdir -p "${VALIDATION_DIR_FOR_LABEL}"
  VALIDATION_IMAGES=$(ls -1 "${TRAIN_DIR_FOR_LABEL}" | gshuf | head -5)
  for IMAGE in ${VALIDATION_IMAGES}; do
    mv -f "${TRAIN_DIR_FOR_LABEL}/${IMAGE}" "${VALIDATION_DIR_FOR_LABEL}"
  done
done < "${LABELS_FILE}"

echo ""
echo ${TRAIN_DIRECTORY}
echo ${VALIDATION_DIRECTORY}
echo ${OUTPUT_DIRECTORY}

# Build the TFRecords version of the image data.
cd "${CURRENT_DIR}"
BUILD_SCRIPT="${WORK_DIR}/build_image_data.py"
OUTPUT_DIRECTORY="${DATA_DIR}"

python "${BUILD_SCRIPT}" \
  --train_directory="${TRAIN_DIRECTORY}" \
  --validation_directory="${VALIDATION_DIRECTORY}" \
  --output_directory="${OUTPUT_DIRECTORY}" \
  --labels_file="${LABELS_FILE}"