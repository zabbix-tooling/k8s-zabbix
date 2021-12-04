from k8sobjects import transform_value


def test_transform_value():
    assert(transform_value("7820m") == "7.82")
    assert (transform_value("512Ki") == "524288")
