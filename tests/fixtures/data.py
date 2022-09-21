# Copyright (C) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

import os
from typing import Callable

import pytest

from geti_sdk.annotation_readers import DatumAnnotationReader


@pytest.fixture(scope="session")
def fxt_blocks_dataset(fxt_base_test_path) -> str:
    """
    This fixture returns the path to the 'blocks' dataset
    """
    yield os.path.join(fxt_base_test_path, "data", "blocks")


@pytest.fixture(scope="session")
def fxt_light_bulbs_dataset(fxt_base_test_path) -> str:
    """
    This fixture returns the path to the 'light-bulbs' dataset
    """
    yield os.path.join(fxt_base_test_path, "data", "../data/light-bulbs")


@pytest.fixture(scope="session")
def fxt_image_folder(fxt_blocks_dataset) -> str:
    """
    This fixture returns the path to a sample image
    """
    yield os.path.join(fxt_blocks_dataset, "images", "NONE")


@pytest.fixture(scope="session")
def fxt_video_folder_light_bulbs(fxt_light_bulbs_dataset) -> str:
    """
    This fixture returns the path to the videos folder in the light bulbs dataset
    """
    yield os.path.join(fxt_light_bulbs_dataset, "videos")


@pytest.fixture(scope="session")
def fxt_image_folder_light_bulbs(fxt_light_bulbs_dataset) -> str:
    """
    This fixture returns the path to the images folder in the light bulbs dataset
    """
    yield os.path.join(fxt_light_bulbs_dataset, "images")


@pytest.fixture(scope="session")
def fxt_image_path(fxt_image_folder) -> str:
    """
    This fixture returns the path to a sample image
    """
    yield os.path.join(fxt_image_folder, "WIN_20220406_21_24_24_Pro.jpg")


@pytest.fixture(scope="session")
def fxt_video_path_1_light_bulbs(fxt_video_folder_light_bulbs) -> str:
    """
    This fixture returns the path to a sample video from the light bulbs dataset
    """
    yield os.path.join(fxt_video_folder_light_bulbs, "Light-Bulb1.mp4")


@pytest.fixture(scope="session")
def fxt_video_path_2_light_bulbs(fxt_video_folder_light_bulbs) -> str:
    """
    This fixture returns the path to a sample video from the light bulbs dataset
    """
    yield os.path.join(fxt_video_folder_light_bulbs, "Light-Bulb2.mp4")


@pytest.fixture(scope="session")
def fxt_image_path_1_light_bulbs(fxt_image_folder_light_bulbs) -> str:
    """
    This fixture returns the path to a sample image from the light bulbs dataset
    """
    yield os.path.join(fxt_image_folder_light_bulbs, "lamp-1523123.jpg")


@pytest.fixture(scope="session")
def fxt_image_path_2_light_bulbs(fxt_image_folder_light_bulbs) -> str:
    """
    This fixture returns the path to a sample image from the light bulbs dataset
    """
    yield os.path.join(fxt_image_folder_light_bulbs, "light-bulb-on-yellow-1426164.jpg")


@pytest.fixture(scope="session")
def fxt_light_bulbs_annotation_path(fxt_light_bulbs_dataset) -> str:
    """
    This fixture returns the path to annotations from the light bulbs project
    """
    yield os.path.join(fxt_light_bulbs_dataset, "annotations")


@pytest.fixture(scope="session")
def fxt_image_path_complex(fxt_image_folder) -> str:
    """
    This fixture returns the path to a complex sample image
    """
    yield os.path.join(fxt_image_folder, "WIN_20220406_21_26_02_Pro.jpg")


@pytest.fixture(scope="function")
def fxt_annotation_reader(fxt_blocks_dataset) -> DatumAnnotationReader:
    """
    This fixture returns a Datumaro Annotation Reader which can read annotations for
    the 'blocks' dataset
    """
    yield DatumAnnotationReader(
        base_data_folder=fxt_blocks_dataset, annotation_format="coco"
    )


@pytest.fixture(scope="function")
def fxt_annotation_reader_grouped(fxt_blocks_dataset) -> DatumAnnotationReader:
    """
    This fixture returns a Datumaro Annotation Reader which can read annotations for
    the 'blocks' dataset. All labels in this reader have been grouped to a single
    'blocks' label.
    """
    reader = DatumAnnotationReader(
        base_data_folder=fxt_blocks_dataset, annotation_format="coco"
    )
    reader.group_labels(labels_to_group=["cube", "cylinder"], group_name="block")
    yield reader


@pytest.fixture(scope="function")
def fxt_annotation_reader_factory(
    fxt_blocks_dataset,
) -> Callable[[None], DatumAnnotationReader]:
    """
    This fixutre returns Datumaro Annotation Readers which can read annotations for
    the 'blocks' dataset. The fixture can be called multiple times to yield different
    instances of the annotation reader
    """

    def _create_annotation_reader() -> DatumAnnotationReader:
        return DatumAnnotationReader(
            base_data_folder=fxt_blocks_dataset, annotation_format="coco"
        )

    yield _create_annotation_reader
