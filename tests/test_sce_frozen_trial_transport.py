from studies.sce_inflation_expectations.evaluation.frozen_trial import expected_transport_provider


def test_transport_validation_uses_registered_provider_with_backward_compatible_default():
    assert expected_transport_provider({"expected_provider": "SiliconFlow"}) == "SiliconFlow"
    assert expected_transport_provider({}) == "DeepInfra"
