def test_package_imports() -> None:
    import fiir_crystal
    import fiir_crystal.discovery
    import fiir_crystal.evaluation
    import fiir_crystal.failure
    import fiir_crystal.fsal
    import fiir_crystal.generation
    import fiir_crystal.predictor

    assert fiir_crystal.__version__ == "0.1.0"
