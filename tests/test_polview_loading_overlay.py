from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from suiteview.polview.ui.loading_overlay import TabLoadingOverlay


def test_loading_disables_underlying_actions_and_restores_original_state(qtbot):
    page = QWidget()
    qtbot.addWidget(page)
    layout = QVBoxLayout(page)
    active = QPushButton("Active")
    inactive = QPushButton("Unavailable")
    inactive.setEnabled(False)
    layout.addWidget(active)
    layout.addWidget(inactive)
    overlay = TabLoadingOverlay(page, "policy")
    page.show()
    overlay.display("Loading")
    assert not active.isEnabled()
    assert not inactive.isEnabled()
    overlay.display("Still loading")
    overlay.hide()
    assert active.isEnabled()
    assert not inactive.isEnabled()


def test_renderer_can_set_new_enabled_state_before_overlay_hides(qtbot):
    page = QWidget()
    qtbot.addWidget(page)
    button = QPushButton("Policy action", page)
    overlay = TabLoadingOverlay(page, "policy")
    overlay.display("Loading")
    overlay.release_controls()
    button.setEnabled(False)
    overlay.hide()
    assert not button.isEnabled()


def test_retry_is_accessible_while_underlying_page_is_disabled(qtbot):
    page = QWidget()
    qtbot.addWidget(page)
    button = QPushButton("Old action", page)
    overlay = TabLoadingOverlay(page, "reinsurance")
    page.show()
    overlay.display("Connection failed", failed=True)
    assert not button.isEnabled()
    assert overlay.retry_button.isEnabled()
    with qtbot.waitSignal(overlay.retry_requested) as signal:
        overlay.retry_button.click()
    assert signal.args == ["reinsurance"]


def test_loading_surface_paints_over_stale_policy_data(qtbot):
    page = QWidget()
    qtbot.addWidget(page)
    page.resize(400, 300)
    stale = QLabel("OLD POLICY", page)
    stale.setGeometry(0, 0, 200, 30)
    stale.setStyleSheet("background: red; color: black;")
    overlay = TabLoadingOverlay(page, "coverages")
    page.show()
    overlay.display("Loading")
    qtbot.wait(10)
    image = page.grab().toImage()
    assert image.pixelColor(5, 5).name() == "#f0f0f0"
