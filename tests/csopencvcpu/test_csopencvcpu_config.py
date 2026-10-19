from copy import deepcopy

from csorchestrator.frontend.cscmake_presets.supported_variants import (
    get_supported_context_os_architecture_list,
)

from csopencvcpu_config import opencv_mapping


def test_opencv_mapping_is_identity_on_supported_contexts() -> None:
    """opencv_mapping must map every supported context to itself."""

    build_matrix = get_supported_context_os_architecture_list()
    assert len(build_matrix) > 0

    for config in build_matrix:
        res = opencv_mapping(deepcopy(config))  # deep copy to be sure
        assert res is not None
        assert res == config


def test_opencv_mapping_does_not_mutate_input() -> None:
    """opencv_mapping must return a copy, leaving the input untouched."""

    build_matrix = get_supported_context_os_architecture_list()
    assert len(build_matrix) > 0

    for config in build_matrix:
        original = deepcopy(config)
        res = opencv_mapping(config)
        assert res is not None
        assert config == original
        assert res == original
        assert res is not config
