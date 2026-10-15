"""Segmentation safeguards, k selection and naming rules."""

import numpy as np
import pandas as pd
import pytest

from retailpulse360 import segmentation
from retailpulse360.features import TARGET


def test_target_is_never_a_segmentation_feature(model_frame):
    with pytest.raises(ValueError):
        segmentation.segment_matrix(model_frame, features=segmentation.SEGMENT_FEATURES + [TARGET])
    assert TARGET not in segmentation.SEGMENT_FEATURES


def test_segment_matrix_is_scaled(model_frame):
    matrix = segmentation.segment_matrix(model_frame)
    np.testing.assert_allclose(matrix.mean(axis=0), 0, atol=1e-9)
    np.testing.assert_allclose(matrix.std(axis=0), 1, atol=1e-9)


def test_choose_k_respects_constraints():
    evaluation = pd.DataFrame(
        {"k": [2, 3, 4, 5], "silhouette": [0.50, 0.20, 0.25, 0.30], "smallest_cluster_pct": [10, 8, 6, 2]}
    )
    # k=2 excluded (min_k=3); k=5 excluded (cluster < 5%); best remaining is k=4.
    assert segmentation.choose_k(evaluation) == 4


def test_kmeans_is_reproducible(model_frame):
    matrix = segmentation.segment_matrix(model_frame)
    first = segmentation.fit_kmeans(matrix, 4).labels_
    second = segmentation.fit_kmeans(matrix, 4).labels_
    assert (first == second).all()


def test_segment_names_are_unique_and_profile_based(model_frame):
    matrix = segmentation.segment_matrix(model_frame)
    labels = segmentation.fit_kmeans(matrix, 4).labels_
    profile = segmentation.profile_segments(model_frame, labels)
    names = segmentation.name_segments(profile)
    assert len(set(names.values())) == len(names)
    lapsed = [c for c, n in names.items() if n.startswith("Lapsed")]
    assert all(profile.loc[c, "frequency_12m"] < 0.5 for c in lapsed)
    assert profile["customers"].sum() == len(model_frame)
