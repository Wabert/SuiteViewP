"""Root conftest — anchors pytest's rootdir on sys.path so tests can import
both ``suiteview`` and ``tools.<bucket>`` modules. Collection is scoped to
``tests/`` via ``testpaths`` in pytest.ini.
"""
