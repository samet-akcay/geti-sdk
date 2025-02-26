# INTEL CONFIDENTIAL
#
# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials, and
# your use of them is governed by the express license under which they were provided to
# you ("License"). Unless the License provides otherwise, you may not use, modify, copy,
# publish, distribute, disclose or transmit this software or the related documents
# without Intel's prior written permission.
#
# This software and the related documents are provided as is,
# with no express or implied warranties, other than those that are expressly stated
# in the License.

"""Module implements the InferenceResultsToPredictionConverter class."""

import abc
import logging
from collections import defaultdict
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

import cv2
import numpy as np
from model_api.models import ImageModel, SegmentationModel
from model_api.models.utils import (
    AnomalyResult,
    ClassificationResult,
    Detection,
    DetectionResult,
    ImageResultWithSoftPrediction,
    InstanceSegmentationResult,
)

from geti_sdk.data_models.annotations import Annotation
from geti_sdk.data_models.containers import LabelList
from geti_sdk.data_models.enums.domain import Domain
from geti_sdk.data_models.label import Label, ScoredLabel
from geti_sdk.data_models.predictions import Prediction
from geti_sdk.data_models.shapes import (
    Ellipse,
    Point,
    Polygon,
    Rectangle,
    RotatedRectangle,
)
from geti_sdk.deployment.predictions_postprocessing.utils.segmentation_utils import (
    create_annotation_from_segmentation_map,
)


class InferenceResultsToPredictionConverter(metaclass=abc.ABCMeta):
    """Interface for the converter"""

    def __init__(self, labels: LabelList, configuration: Dict[str, Any]):
        self.labels = labels.get_non_empty_labels()
        model_api_labels = configuration["labels"]
        # configuration["labels"] can be a single string or a list of strings
        model_api_labels = (
            [model_api_labels]
            if isinstance(model_api_labels, str)
            else [str(name) for name in model_api_labels]
        )
        # Create a mapping of label ID to label objects
        self.label_map_ids = {}
        # Legacy OTX (<2.0) model configuration contains label names (without spaces) instead of IDs
        self.legacy_label_map_names = defaultdict(list)

        # get the first empty label
        self.empty_label = labels.get_empty_label()

        for i, label in enumerate(labels):
            self.label_map_ids[str(label.id)] = label
            # Using a dict of list to handle duplicates label names (e.g. "foo bar", "foo_bar")
            self.legacy_label_map_names[label.name.replace(" ", "_")].append(label)
            self.legacy_label_map_names[label.name].append(label)
        self.legacy_label_map_names["otx_empty_lbl"] = [self.empty_label]

        # Create a mapping of ModelAPI label indices to label objects
        self.idx_to_label = {}
        self.str_to_label = {}
        self.model_api_label_map_counts: dict[str, int] = defaultdict(int)
        for i, label_str in enumerate(model_api_labels):
            label = self.__get_label(
                label_str, pos_idx=self.model_api_label_map_counts[label_str]
            )
            self.idx_to_label[i] = label
            self.str_to_label[label_str] = label
            self.model_api_label_map_counts[label_str] += 1
        logging.info(
            f"Converter loaded labels with following indices: {self.idx_to_label}"
        )

    def __get_label(self, label_str: str, pos_idx: int) -> Label:
        if label_str in self.label_map_ids:
            return self.label_map_ids[label_str]
        matched_legacy_labels = self.legacy_label_map_names[label_str]
        if pos_idx < len(matched_legacy_labels):
            return matched_legacy_labels[pos_idx]
        raise ValueError(
            f"Label '{label_str}' (pos_idx={pos_idx}) not found in the label schema"
        )

    def get_label_by_idx(self, label_idx: int) -> Label:
        """
        Get a Label object by its index. It is useful for converting ModelAPI results to Prediction.

        :param label_idx: index of the label from prediction results
        :return: Label corresponding to the index
        """
        return self.idx_to_label[label_idx]

    def get_label_by_str(self, label_str: int) -> Label:
        """
        Get a Label object by its string representation. It is useful for converting ModelAPI results to Prediction.

        :param label_str: string representation of the label from prediction results
        :return: Label corresponding to the string
        """
        return self.str_to_label[label_str]

    @abc.abstractmethod
    def convert_to_prediction(
        self, inference_results: NamedTuple, **kwargs
    ) -> Prediction:
        """
        Convert raw inference results to the Prediction format.

        :param inference_results: raw predictions from inference
        :return: Prediction object containing the shapes obtained from the raw predictions.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def convert_saliency_map(
        self, inference_results: NamedTuple, **kwargs
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Extract a saliency map from inference results and return in a unified format.

        :param inference_results: raw predictions from inference
        :return: Prediction object containing the shapes obtained from the raw predictions.
        """
        raise NotImplementedError


class ClassificationToPredictionConverter(InferenceResultsToPredictionConverter):
    """
    Converts ModelAPI Classification predictions to Prediction object.

    :param labels: LabelList containing the label info of the task
    :param configuration: configuration dictionary containing additional
        parameters
    """

    def __init__(self, labels: LabelList, configuration: Dict[str, Any]):
        super().__init__(labels, configuration)

    def convert_to_prediction(
        self,
        inference_results: ClassificationResult,
        image_shape: Tuple[int, int, int],
        **kwargs,
    ) -> Prediction:  # noqa: ARG003
        """
        Convert ModelAPI ClassificationResult inference results to Prediction object.

        :param inference_results: classification labels represented in ModelAPI format (label_index, label_name, confidence)
        :param image_shape: shape of the input image
        :return: Prediction object with corresponding label
        """
        labels = []
        for label in inference_results.top_labels:
            label_idx, label_name, label_prob = label
            scored_label = ScoredLabel.from_label(
                label=self.get_label_by_idx(label_idx), probability=label_prob
            )
            labels.append(scored_label)

        if not labels and self.empty_label:
            labels = [ScoredLabel.from_label(self.empty_label, probability=0)]

        annotations = Annotation(
            shape=Rectangle.generate_full_box(image_shape[1], image_shape[0]),
            labels=labels,
        )
        return Prediction([annotations])

    def convert_saliency_map(
        self,
        inference_results: NamedTuple,
        image_shape: Tuple[int, int, int],
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Extract a saliency map from inference results and return in a unified format.

        :param inference_results: classification labels represented in ModelAPI format (label_index, label_name, confidence)
        :param image_shape: shape of the input image
        :return: Prediction object with corresponding label
        """
        saliency_map = inference_results.saliency_map
        if len(saliency_map) == 0:
            return None
        saliency_map = cv2.resize(
            np.transpose(saliency_map.squeeze(0), (1, 2, 0)),
            dsize=(image_shape[1], image_shape[0]),
            interpolation=cv2.INTER_CUBIC,
        )
        if len(saliency_map.shape) == 2:
            saliency_map = np.expand_dims(saliency_map, axis=-1)
        saliency_map = np.transpose(saliency_map, (2, 0, 1))  # shape: (N classes, h, w)
        return {
            label.name: saliency_map[i]
            for i, label in enumerate(self.labels.get_non_empty_labels())
        }

    def _get_label_by_prediction_name(self, name: str) -> Label:
        """
        Get a Label object by its predicted name.

        :param name: predicted name of the label
        :return: Label corresponding to the name
        :raises KeyError: if the label is not found in the LabelList
        """
        try:
            return self.labels.get_by_name(name=name)
        except KeyError:
            # If the label is not found, we try to find it by legacy name (replacing spaces with underscores)
            for label in self.labels:
                legacy_name = label.name.replace(" ", "_")
                if legacy_name == name:
                    logging.warning(
                        f"Found label `{label.name}` using its legacy name `{legacy_name}`."
                    )
                    return label
        raise KeyError(f"Label named `{name}` was not found in the LabelList")


class DetectionToPredictionConverter(InferenceResultsToPredictionConverter):
    """
    Converts ModelAPI Detection objects to Prediction object.

    :param labels: LabelList containing the label info of the task
    :param configuration: optional model configuration setting
    """

    def __init__(self, labels: LabelList, configuration: Dict[str, Any]):
        super().__init__(labels, configuration)
        self.use_ellipse_shapes = False
        self.confidence_threshold = 0.0
        if "use_ellipse_shapes" in configuration:
            self.use_ellipse_shapes = configuration["use_ellipse_shapes"]
        if "confidence_threshold" in configuration:
            self.confidence_threshold = configuration["confidence_threshold"]

    def _detection2array(self, detections: List[Detection]) -> np.ndarray:
        """
        Convert list of OpenVINO Detection to a numpy array.

        :param detections: list of OpenVINO Detection containing [score, id, xmin, ymin, xmax, ymax]
        :return: numpy array with [label, confidence, x1, y1, x2, y2]
        """
        scores = np.empty((0, 1), dtype=np.float32)
        labels = np.empty((0, 1), dtype=np.uint32)
        boxes = np.empty((0, 4), dtype=np.float32)
        for det in detections:
            if (det.xmax - det.xmin) * (det.ymax - det.ymin) < 1.0:
                continue
            scores = np.append(scores, [[det.score]], axis=0)
            labels = np.append(labels, [[det.id]], axis=0)
            boxes = np.append(
                boxes,
                [[float(det.xmin), float(det.ymin), float(det.xmax), float(det.ymax)]],
                axis=0,
            )
        return np.concatenate((labels, scores, boxes), -1)

    def convert_to_prediction(
        self, inference_results: DetectionResult, **kwargs
    ) -> Prediction:
        """
        Convert ModelAPI DetectionResult inference results to Prediction object.

        :param inference_results: detection represented in ModelAPI format (label, confidence, x1, y1, x2, y2).

        _Note:
            - `label` can be any integer that can be mapped to `self.labels`
            - `confidence` should be a value between 0 and 1
            - `x1`, `x2`, `y1` and `y2` are expected to be in pixel
        :return: Prediction object containing the boxes obtained from the prediction
        """
        detections = self._detection2array(inference_results.objects)

        annotations = []
        if (
            len(detections)
            and detections.shape[1:] < (6,)
            or detections.shape[1:] > (7,)
        ):
            raise ValueError(
                f"Shape of prediction is not expected, expected (n, 7) or (n, 6) but got {detections.shape}"
            )

        for detection in detections:
            # Some OpenVINO models use an output shape of [7,]
            # If this is the case, skip the first value as it is not used
            _detection = detection[1:] if detection.shape == (7,) else detection

            label_index = int(_detection[0])
            confidence = _detection[1]
            scored_label = ScoredLabel.from_label(
                self.get_label_by_idx(label_index), confidence
            )
            coords = _detection[2:]
            shape: Union[Ellipse, Rectangle]

            if confidence < self.confidence_threshold:
                continue

            bbox_width = coords[2] - coords[0]
            bbox_height = coords[3] - coords[1]
            if self.use_ellipse_shapes:
                shape = Ellipse(coords[0], coords[1], bbox_width, bbox_height)
            else:
                shape = Rectangle(coords[0], coords[1], bbox_width, bbox_height)

            annotation = Annotation(shape=shape, labels=[scored_label])
            annotations.append(annotation)
        return Prediction(annotations)

    def convert_saliency_map(
        self,
        inference_results: NamedTuple,
        image_shape: Tuple[int, int, int],
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Extract a saliency map from inference results and return in a unified format.

        :param inference_results: classification labels represented in ModelAPI format (label_index, label_name, confidence)
        :param image_shape: shape of the input image
        :return: Prediction object with corresponding label
        """
        saliency_map = inference_results.saliency_map
        if len(saliency_map) == 0:
            return None
        if isinstance(saliency_map, list):
            saliency_map = np.array(
                [
                    smap if len(smap) > 0 else np.zeros(image_shape[:2], dtype=np.uint8)
                    for smap in saliency_map
                ]
            )
        elif isinstance(saliency_map, np.ndarray):
            saliency_map = saliency_map.squeeze(0)
        else:
            raise ValueError(
                f"Unsupported saliency map type: {type(saliency_map)}. Expected list or numpy array."
            )
        saliency_map = cv2.resize(
            np.transpose(saliency_map, (1, 2, 0)),
            dsize=(image_shape[1], image_shape[0]),
            interpolation=cv2.INTER_CUBIC,
        )
        if len(saliency_map.shape) == 2:
            saliency_map = np.expand_dims(saliency_map, axis=-1)
        saliency_map = np.transpose(saliency_map, (2, 0, 1))  # shape: (N classes, h, w)
        return {label.name: saliency_map[i] for i, label in enumerate(self.labels)}


class RotatedRectToPredictionConverter(DetectionToPredictionConverter):
    """
    Converts ModelAPI Rotated Detection objects to Prediction.
    """

    def convert_to_prediction(
        self, inference_results: InstanceSegmentationResult, **kwargs
    ) -> Prediction:
        """
        Convert ModelAPI instance segmentation inference results to a rotated bounding box annotation format.

        :param inference_results: segmentation represented in ModelAPI format
        :return: Prediction object containing the rotated boxes obtained from the segmentation contours
        :raises ValueError: if metadata is missing from the preprocess step
        """
        annotations = []
        shape: Union[RotatedRectangle, Ellipse]
        for obj in inference_results.segmentedObjects:
            label = self.get_label_by_idx(obj.id)
            if obj.score < self.confidence_threshold or label.is_empty:
                continue
            if self.use_ellipse_shapes:
                shape = Ellipse(
                    obj.xmin, obj.ymin, obj.xmax - obj.xmin, obj.ymax - obj.ymin
                )
                annotations.append(
                    Annotation(
                        shape=shape,
                        labels=[ScoredLabel.from_label(label, float(obj.score))],
                    )
                )
            else:
                mask = obj.mask.astype(np.uint8)
                contours, hierarchies = cv2.findContours(
                    mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
                )
                if hierarchies is None:
                    continue
                for contour, hierarchy in zip(contours, hierarchies[0]):
                    if hierarchy[3] != -1:
                        continue
                    if len(contour) <= 2 or cv2.contourArea(contour) < 1.0:
                        continue
                    points = [
                        Point(
                            x=point[0],
                            y=point[1],
                        )
                        for point in cv2.boxPoints(cv2.minAreaRect(contour))
                    ]
                    shape = Polygon(points=points)
                    annotations.append(
                        Annotation(
                            shape=RotatedRectangle.from_polygon(shape),
                            labels=[ScoredLabel.from_label(label, float(obj.score))],
                        )
                    )
        return Prediction(annotations)


class MaskToAnnotationConverter(DetectionToPredictionConverter):
    """
    Converts DetectionBox Predictions ModelAPI to Prediction object.
    """

    def convert_to_prediction(
        self, inference_results: Any, **kwargs: Dict[str, Any]
    ) -> Prediction:
        """
        Convert inference results to Prediction object.

        :param inference_results: Raw inference results from the model.
        :return: Prediction object.
        """
        annotations = []
        shape: Union[Polygon, Ellipse]
        for obj in inference_results.segmentedObjects:
            if obj.score < self.confidence_threshold:
                continue
            if self.use_ellipse_shapes:
                shape = Ellipse(
                    obj.xmin, obj.ymin, obj.xmax - obj.xmin, obj.ymax - obj.ymin
                )
                annotations.append(
                    Annotation(
                        shape=shape,
                        labels=[
                            ScoredLabel.from_label(
                                self.get_label_by_idx(obj.id), float(obj.score)
                            )
                        ],
                    )
                )
            else:
                mask = obj.mask.astype(np.uint8)
                contours, hierarchies = cv2.findContours(
                    mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
                )
                if hierarchies is None:
                    continue
                for contour, hierarchy in zip(contours, hierarchies[0]):
                    if hierarchy[3] != -1:
                        continue
                    if len(contour) <= 2 or cv2.contourArea(contour) < 1.0:
                        continue
                    contour = list(contour)
                    points = [
                        Point(
                            x=point[0][0],
                            y=point[0][1],
                        )
                        for point in contour
                    ]
                    shape = Polygon(points=points)
                    annotations.append(
                        Annotation(
                            shape=shape,
                            labels=[
                                ScoredLabel.from_label(
                                    self.get_label_by_idx(obj.id), float(obj.score)
                                )
                            ],
                        )
                    )
        return Prediction(annotations)

    def convert_saliency_map(
        self,
        inference_results: NamedTuple,
        image_shape: Tuple[int, int, int],
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Extract a saliency map from inference results and return in a unified format.

        :param inference_results: classification labels represented in ModelAPI format (label_index, label_name, confidence)
        :param image_shape: shape of the input image
        :return: Prediction object with corresponding label
        """
        if len(inference_results.saliency_map) == 0:
            return None
        # Model API returns a list of np.ndarray for each label
        # Including `no_object` which is empty
        saliency_map = np.array(
            [
                smap if len(smap) > 0 else np.zeros(image_shape[:2], dtype=np.uint8)
                for smap in inference_results.saliency_map
            ]
        )  # shape: (N classes, h, w)
        return {label.name: saliency_map[i] for i, label in enumerate(self.labels)}


class SegmentationToPredictionConverter(InferenceResultsToPredictionConverter):
    """
    Converts ModelAPI Segmentation objects to Prediction object.

    :param labels: LabelList containing the label info of the task
    :param configuration: model configuration setting
    :param model: SegmentationModel instance, needed for getting contours
    """

    def __init__(
        self, labels: LabelList, configuration: Dict[str, Any], model: SegmentationModel
    ):
        super().__init__(labels, configuration)
        self.model = model

    def get_label_by_idx(self, label_idx: int) -> Label:
        """
        Get a Label object by its index. It is useful for converting ModelAPI results to Prediction.

        # NB: For segmentation results, index=0 is reserved for the background label

        :param label_idx: index of the label from prediction results
        :return: Label corresponding to the index
        """
        self.idx_to_label[-1] = self.empty_label
        return super().get_label_by_idx(label_idx - 1)

    def convert_to_prediction(
        self, inference_results: ImageResultWithSoftPrediction, **kwargs  # noqa: ARG002
    ) -> Prediction:
        """
        Convert ModelAPI instance segmentation inference results to Prediction object.

        :param inference_results: segmentation represented in ModelAPI format
        :return: Prediction object containing the contour polygon obtained from the segmentation
        """
        contours = self.model.get_contours(inference_results)

        annotations: list[Annotation] = []
        for contour in contours:
            label = self.get_label_by_str(contour.label)
            if len(contour.shape) > 0 and not label.is_empty:
                approx_curve = cv2.approxPolyDP(contour.shape, 1.0, True)
                if len(approx_curve) > 2:
                    points = [Point(x=p[0][0], y=p[0][1]) for p in contour.shape]
                    annotations.append(
                        Annotation(
                            shape=Polygon(points=points),
                            labels=[
                                ScoredLabel.from_label(
                                    label=label, probability=contour.probability
                                )
                            ],
                        )
                    )
        return Prediction(annotations)

    def convert_saliency_map(
        self,
        inference_results: NamedTuple,
        image_shape: Tuple[int, int, int],
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Extract a saliency map from inference results and return in a unified format.

        :param inference_results: classification labels represented in ModelAPI format (label_index, label_name, confidence)
        :param image_shape: shape of the input image
        :return: Prediction object with corresponding label
        """
        saliency_map = inference_results.saliency_map
        if len(saliency_map) == 0:
            return None
        saliency_map = np.transpose(saliency_map, (2, 0, 1))  # shape: (N classes, h, w)
        return {
            label.name: saliency_map[i]
            for i, label in self.idx_to_label.items()
            if not label.is_empty
        }


class AnomalyToPredictionConverter(InferenceResultsToPredictionConverter):
    """
    Convert ModelAPI AnomalyResult predictions to Prediction object.

    :param labels: LabelList containing the label info of the task
    :param configuration: model configuration setting
    """

    def __init__(self, labels: LabelList, configuration: Dict[str, Any]):
        self.normal_label = next(label for label in labels if not label.is_anomalous)
        self.anomalous_label = next(label for label in labels if label.is_anomalous)
        if configuration is not None and "domain" in configuration:
            self.domain = configuration["domain"]

    def convert_to_prediction(
        self, inference_results: AnomalyResult, image_shape: Tuple[int], **kwargs
    ) -> Prediction:  # noqa: ARG002
        """
        Convert ModelAPI AnomalyResult inferenceresults to sc_sdk annotations.

        :param inference_results: anomaly result represented in ModelAPI format (same for all anomaly tasks)
        :return: Prediction object based on the specific anomaly task:
            - Classification: single label (normal or anomalous).
            - Segmentation: contour polygon representing the segmentation.
            - Detection: predicted bounding boxes.
        """
        pred_label = inference_results.pred_label
        label = (
            self.anomalous_label
            if pred_label.lower() in ("anomaly", "anomalous")
            else self.normal_label
        )
        annotations: List[Annotation] = []
        if (
            self.domain == Domain.ANOMALY_CLASSIFICATION
            or self.domain == Domain.ANOMALY
        ):
            scored_label = ScoredLabel.from_label(
                label=label, probability=float(inference_results.pred_score)
            )
            annotations = [
                Annotation(
                    shape=Rectangle.generate_full_box(*image_shape[1::-1]),
                    labels=[scored_label],
                )
            ]
        elif self.domain == Domain.ANOMALY_SEGMENTATION:
            annotations = create_annotation_from_segmentation_map(
                hard_prediction=inference_results.pred_mask,
                soft_prediction=inference_results.anomaly_map.squeeze(),
                label_map={0: self.normal_label, 1: self.anomalous_label},
            )
        elif self.domain == Domain.ANOMALY_DETECTION:
            for box in inference_results.pred_boxes:
                annotations.append(
                    Annotation(
                        shape=Rectangle(
                            box[0], box[1], box[2] - box[0], box[3] - box[1]
                        ),
                        labels=[
                            ScoredLabel.from_label(
                                label=self.anomalous_label,
                                probability=inference_results.pred_score,
                            )
                        ],
                    )
                )
        else:
            raise ValueError(
                f"Cannot convert inference results for task '{self.domain.name}'. Only Anomaly tasks are supported."
            )
        if not annotations:
            scored_label = ScoredLabel.from_label(
                label=self.normal_label, probability=0
            )
            annotations = [
                Annotation(
                    labels=[scored_label],
                    shape=Rectangle.generate_full_box(*image_shape[1::-1]),
                )
            ]
        return Prediction(annotations)

    def convert_saliency_map(
        self,
        inference_results: NamedTuple,
        image_shape: Tuple[int, int, int],
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Extract a saliency map from inference results and return in a unified format.

        :param inference_results: classification labels represented in ModelAPI format (label_index, label_name, confidence)
        :param image_shape: shape of the input image
        :return: Prediction object with corresponding label
        """
        # Normalizing Anomaly map
        saliency_map = inference_results.anomaly_map
        saliency_map -= saliency_map.min()
        saliency_map = saliency_map / (saliency_map.max() + 1e-12) * 255
        saliency_map = np.round(saliency_map).astype(np.uint8)  # shape: (h, w)
        return {self.anomalous_label.name: saliency_map}


class ConverterFactory:
    """
    Factory class for creating inference result to prediction converters based on the model's task.
    """

    @staticmethod
    def create_converter(
        labels: LabelList,
        domain: Domain,
        configuration: Dict[str, Any],
        model: ImageModel,
    ) -> InferenceResultsToPredictionConverter:
        """
        Create the appropriate inference converter object according to the model's task.

        :param labels: The labels of the model
        :param domain: The domain to which the converter applies
        :param configuration: configuration for the converter
        :param model: ImageModel instance
        :return: The created inference result to prediction converter.
        :raises ValueError: If the task type cannot be determined from the label schema.
        """
        if domain == Domain.CLASSIFICATION:
            return ClassificationToPredictionConverter(labels, configuration)
        if domain == Domain.DETECTION:
            return DetectionToPredictionConverter(labels, configuration)
        if domain == Domain.SEGMENTATION:
            return SegmentationToPredictionConverter(labels, configuration, model=model)
        if domain == Domain.ROTATED_DETECTION:
            return RotatedRectToPredictionConverter(labels, configuration)
        if domain == Domain.INSTANCE_SEGMENTATION:
            return MaskToAnnotationConverter(labels, configuration)
        if domain in (
            Domain.ANOMALY_CLASSIFICATION,
            Domain.ANOMALY_SEGMENTATION,
            Domain.ANOMALY_DETECTION,
            Domain.ANOMALY,
        ):
            configuration.update({"domain": domain})
            return AnomalyToPredictionConverter(labels, configuration)
        raise ValueError(f"Cannot create inferencer for task type '{domain.name}'.")
