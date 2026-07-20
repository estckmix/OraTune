"""Settings Dialog - Multi-provider AI configuration"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QDialogButtonBox,
    QCheckBox,
    QComboBox,
    QTabWidget,
    QWidget,
)
import json
from typing import Any

import keyring
from keyring.errors import KeyringError

from services.ai_service import KEYRING_SERVICE, SETTINGS_PATH, get_secret

SETTINGS_FILE = str(SETTINGS_PATH)

_SECRET_FIELDS = ("anthropic_key", "openai_key", "azure_key", "copilot_key")


def _store_secret(name: str, value: str) -> None:
    """Persist a secret in the OS credential store, or clear it when blank."""
    try:
        if value:
            keyring.set_password(KEYRING_SERVICE, name, value)
        else:
            keyring.delete_password(KEYRING_SERVICE, name)
    except KeyringError:
        pass  # No secure backend available — do not fall back to plaintext


PROVIDERS = ["Claude (Anthropic)", "ChatGPT (OpenAI)", "Azure OpenAI", "GitHub Copilot"]
PROVIDER_KEYS = ["anthropic", "openai", "azure", "copilot"]

ANTHROPIC_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-haiku-4-5-20251001",
]
OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
]
COPILOT_MODELS = [
    "gpt-4o",
    "gpt-4",
    "gpt-3.5-turbo",
]


def load_settings() -> dict[str, Any]:
    """Settings JSON is schemaless at this boundary — legacy keys round-trip."""
    try:
        with open(SETTINGS_FILE, "r") as f:
            loaded: dict[str, Any] = json.load(f)
            return loaded
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict[str, Any]) -> None:
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def get_active_provider() -> str:
    """Return the active provider key e.g. 'anthropic', 'openai', 'azure', 'copilot'"""
    s = load_settings()
    provider: str = s.get("active_provider", "anthropic")
    return provider


def _make_key_row(
    placeholder: str, saved_value: str = ""
) -> tuple[QWidget, QLineEdit, QPushButton]:
    """
    Build a password input row.
    Returns (QWidget container, QLineEdit, QPushButton toggle).
    Caller adds the returned widget to its own layout.
    """
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)

    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    field.setPlaceholderText(placeholder)
    if saved_value:
        field.setText(saved_value)
    row.addWidget(field)

    toggle = QPushButton("Show")
    toggle.setFixedWidth(56)
    toggle.setCheckable(True)

    def _apply_visibility(checked: bool) -> None:
        field.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
        toggle.setText("Hide" if checked else "Show")

    toggle.toggled.connect(_apply_visibility)
    row.addWidget(toggle)
    return container, field, toggle


def _result_label() -> QLabel:
    lbl = QLabel("")
    lbl.setStyleSheet("background: transparent; font-size: 11px;")
    return lbl


def _set_result(lbl: QLabel, ok: bool, msg: str) -> None:
    color = "#2ea043" if ok else "#f85149"
    lbl.setText(msg)
    lbl.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent;")


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings — AI Provider Configuration")
        self.setMinimumWidth(580)
        self.setMinimumHeight(520)
        self.setModal(True)
        self.settings: dict[str, Any] = load_settings()
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 20)

        # Active provider selector
        active_group = QGroupBox("ACTIVE AI PROVIDER")
        ag_layout = QFormLayout(active_group)
        ag_layout.setSpacing(8)

        self.provider_combo = QComboBox()
        for p in PROVIDERS:
            self.provider_combo.addItem(p)
        saved_key = self.settings.get("active_provider", "anthropic")
        if saved_key in PROVIDER_KEYS:
            self.provider_combo.setCurrentIndex(PROVIDER_KEYS.index(saved_key))
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        ag_layout.addRow("Active provider:", self.provider_combo)

        self.active_status = QLabel("")
        self.active_status.setStyleSheet(
            "color: #888888; font-size: 11px; background: transparent;"
        )
        ag_layout.addRow("", self.active_status)

        root.addWidget(active_group)

        # Per-provider tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_anthropic_tab(), "Claude")
        self.tabs.addTab(self._build_openai_tab(), "ChatGPT")
        self.tabs.addTab(self._build_azure_tab(), "Azure OpenAI")
        self.tabs.addTab(self._build_copilot_tab(), "GitHub Copilot")
        root.addWidget(self.tabs)

        # Analysis preferences
        pref_group = QGroupBox("ANALYSIS PREFERENCES")
        pf = QFormLayout(pref_group)
        pf.setSpacing(8)
        self.auto_analyze_check = QCheckBox("Auto-analyze when files are loaded")
        self.auto_analyze_check.setChecked(self.settings.get("auto_analyze", False))
        self.auto_analyze_check.setStyleSheet("background: transparent;")
        pf.addRow("", self.auto_analyze_check)
        root.addWidget(pref_group)

        # Dialog buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

        self._refresh_active_status()

    # ── Provider tabs ─────────────────────────────────────────────────────────

    def _build_anthropic_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        info = QLabel(
            "Anthropic API key — get yours at console.anthropic.com\n"
            "Key is stored locally and sent only to api.anthropic.com."
        )
        info.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        _ant_row, self.ant_key, _ = _make_key_row(
            "sk-ant-...",
            get_secret("anthropic_key"),
        )
        form.addRow("API Key:", _ant_row)

        self.ant_model = QComboBox()
        self.ant_model.addItems(ANTHROPIC_MODELS)
        saved = self.settings.get("anthropic_model", ANTHROPIC_MODELS[0])
        idx = self.ant_model.findText(saved)
        if idx >= 0:
            self.ant_model.setCurrentIndex(idx)
        form.addRow("Model:", self.ant_model)
        lay.addLayout(form)

        test_btn = QPushButton("Test Connection")
        self.ant_result = _result_label()
        test_btn.clicked.connect(lambda: self._test_anthropic(test_btn))
        lay.addWidget(test_btn)
        lay.addWidget(self.ant_result)
        lay.addStretch()
        return w

    def _build_openai_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        info = QLabel(
            "OpenAI API key — get yours at platform.openai.com\n"
            "Key is stored locally and sent only to api.openai.com."
        )
        info.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        _oai_row, self.oai_key, _ = _make_key_row("sk-...", get_secret("openai_key"))
        form.addRow("API Key:", _oai_row)

        self.oai_model = QComboBox()
        self.oai_model.addItems(OPENAI_MODELS)
        saved = self.settings.get("openai_model", OPENAI_MODELS[0])
        idx = self.oai_model.findText(saved)
        if idx >= 0:
            self.oai_model.setCurrentIndex(idx)
        form.addRow("Model:", self.oai_model)
        lay.addLayout(form)

        test_btn = QPushButton("Test Connection")
        self.oai_result = _result_label()
        test_btn.clicked.connect(lambda: self._test_openai(test_btn))
        lay.addWidget(test_btn)
        lay.addWidget(self.oai_result)
        lay.addStretch()
        return w

    def _build_azure_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        info = QLabel(
            "Azure OpenAI — requires an Azure subscription with OpenAI resource.\n"
            "Endpoint and deployment name are set in your Azure portal.\n"
            "Key is stored locally and sent only to your Azure endpoint."
        )
        info.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()

        self.az_endpoint = QLineEdit()
        self.az_endpoint.setPlaceholderText("https://YOUR-RESOURCE.openai.azure.com/")
        self.az_endpoint.setText(self.settings.get("azure_endpoint", ""))
        form.addRow("Endpoint URL:", self.az_endpoint)

        _az_row, self.az_key, _ = _make_key_row(
            "Azure API key...",
            get_secret("azure_key"),
        )
        form.addRow("API Key:", _az_row)

        self.az_deployment = QLineEdit()
        self.az_deployment.setPlaceholderText("my-gpt4-deployment")
        self.az_deployment.setText(self.settings.get("azure_deployment", ""))
        form.addRow("Deployment name:", self.az_deployment)

        self.az_api_version = QComboBox()
        self.az_api_version.addItems(
            [
                "2024-02-01",
                "2024-05-01-preview",
                "2023-12-01-preview",
                "2023-07-01-preview",
            ]
        )
        saved_ver = self.settings.get("azure_api_version", "2024-02-01")
        idx = self.az_api_version.findText(saved_ver)
        if idx >= 0:
            self.az_api_version.setCurrentIndex(idx)
        form.addRow("API version:", self.az_api_version)

        lay.addLayout(form)

        test_btn = QPushButton("Test Connection")
        self.az_result = _result_label()
        test_btn.clicked.connect(lambda: self._test_azure(test_btn))
        lay.addWidget(test_btn)
        lay.addWidget(self.az_result)
        lay.addStretch()
        return w

    def _build_copilot_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        info = QLabel(
            "GitHub Copilot API — requires an active GitHub Copilot subscription.\n"
            "Uses a GitHub personal access token (PAT) with Copilot scope.\n"
            "Generate your token at github.com → Settings → Developer settings → PAT.\n"
            "Key is stored locally and sent only to api.githubcopilot.com."
        )
        info.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        _cop_row, self.cop_key, _ = _make_key_row(
            "github_pat_...",
            get_secret("copilot_key"),
        )
        form.addRow("Token:", _cop_row)

        self.cop_model = QComboBox()
        self.cop_model.addItems(COPILOT_MODELS)
        saved = self.settings.get("copilot_model", COPILOT_MODELS[0])
        idx = self.cop_model.findText(saved)
        if idx >= 0:
            self.cop_model.setCurrentIndex(idx)
        form.addRow("Model:", self.cop_model)
        lay.addLayout(form)

        # Copilot endpoint note
        note = QLabel(
            "Endpoint: https://api.githubcopilot.com  (fixed, no configuration needed)"
        )
        note.setStyleSheet("color: #555555; font-size: 10px; background: transparent;")
        lay.addWidget(note)

        test_btn = QPushButton("Test Connection")
        self.cop_result = _result_label()
        test_btn.clicked.connect(lambda: self._test_copilot(test_btn))
        lay.addWidget(test_btn)
        lay.addWidget(self.cop_result)
        lay.addStretch()
        return w

    # ── Connection tests ──────────────────────────────────────────────────────

    def _test_anthropic(self, btn: QPushButton) -> None:
        key = self.ant_key.text().strip()
        if not key:
            _set_result(self.ant_result, False, "⚠ No API key entered")
            return
        btn.setEnabled(False)
        self.ant_result.setText("Testing...")
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=key)
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            _set_result(self.ant_result, True, "✓ Connected — Claude ready")
        except Exception as e:
            _set_result(self.ant_result, False, f"✕ {str(e)[:90]}")
        finally:
            btn.setEnabled(True)

    def _test_openai(self, btn: QPushButton) -> None:
        key = self.oai_key.text().strip()
        if not key:
            _set_result(self.oai_result, False, "⚠ No API key entered")
            return
        btn.setEnabled(False)
        self.oai_result.setText("Testing...")
        try:
            from openai import OpenAI

            client = OpenAI(api_key=key)
            client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=5,
                messages=[{"role": "user", "content": "Hi"}],
            )
            _set_result(self.oai_result, True, "✓ Connected — ChatGPT ready")
        except Exception as e:
            _set_result(self.oai_result, False, f"✕ {str(e)[:90]}")
        finally:
            btn.setEnabled(True)

    def _test_azure(self, btn: QPushButton) -> None:
        key = self.az_key.text().strip()
        endpoint = self.az_endpoint.text().strip()
        deployment = self.az_deployment.text().strip()
        api_version = self.az_api_version.currentText()
        if not all([key, endpoint, deployment]):
            _set_result(
                self.az_result,
                False,
                "⚠ Endpoint, key and deployment name are all required",
            )
            return
        btn.setEnabled(False)
        self.az_result.setText("Testing...")
        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                api_key=key,
                azure_endpoint=endpoint,
                api_version=api_version,
            )
            client.chat.completions.create(
                model=deployment,
                max_tokens=5,
                messages=[{"role": "user", "content": "Hi"}],
            )
            _set_result(self.az_result, True, "✓ Connected — Azure OpenAI ready")
        except Exception as e:
            _set_result(self.az_result, False, f"✕ {str(e)[:90]}")
        finally:
            btn.setEnabled(True)

    def _test_copilot(self, btn: QPushButton) -> None:
        key = self.cop_key.text().strip()
        if not key:
            _set_result(self.cop_result, False, "⚠ No GitHub token entered")
            return
        btn.setEnabled(False)
        self.cop_result.setText("Testing...")
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=key,
                base_url="https://api.githubcopilot.com",
            )
            client.chat.completions.create(
                model=self.cop_model.currentText(),
                max_tokens=5,
                messages=[{"role": "user", "content": "Hi"}],
            )
            _set_result(self.cop_result, True, "✓ Connected — GitHub Copilot ready")
        except Exception as e:
            _set_result(self.cop_result, False, f"✕ {str(e)[:90]}")
        finally:
            btn.setEnabled(True)

    # ── Provider change ───────────────────────────────────────────────────────

    def _on_provider_changed(self, idx: int) -> None:
        self._refresh_active_status()

    def _refresh_active_status(self) -> None:
        idx = self.provider_combo.currentIndex()
        provider_key = PROVIDER_KEYS[idx]
        has_key = self._provider_has_key(provider_key)
        if has_key:
            self.active_status.setText(f"● Key configured for {PROVIDERS[idx]}")
            self.active_status.setStyleSheet(
                "color: #2ea043; font-size: 11px; background: transparent;"
            )
        else:
            self.active_status.setText(
                "⚠ No key configured — will fall back to offline mode"
            )
            self.active_status.setStyleSheet(
                "color: #e3b341; font-size: 11px; background: transparent;"
            )

    def _provider_has_key(self, key: str) -> bool:
        def has(name: str) -> bool:
            return bool(get_secret(name))

        key_map = {
            "anthropic": has("anthropic_key"),
            "openai": has("openai_key"),
            "azure": has("azure_key") and bool(self.settings.get("azure_endpoint", "")),
            "copilot": has("copilot_key"),
        }
        return bool(key_map.get(key, False))

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        idx = self.provider_combo.currentIndex()
        self.settings["active_provider"] = PROVIDER_KEYS[idx]

        # API keys → OS credential store only, never the settings JSON
        _store_secret("anthropic_key", self.ant_key.text().strip())
        _store_secret("openai_key", self.oai_key.text().strip())
        _store_secret("azure_key", self.az_key.text().strip())
        _store_secret("copilot_key", self.cop_key.text().strip())

        # Non-secret settings → JSON
        self.settings["anthropic_model"] = self.ant_model.currentText()
        self.settings["model"] = self.settings["anthropic_model"]  # legacy mirror
        self.settings["openai_model"] = self.oai_model.currentText()
        self.settings["azure_endpoint"] = self.az_endpoint.text().strip()
        self.settings["azure_deployment"] = self.az_deployment.text().strip()
        self.settings["azure_api_version"] = self.az_api_version.currentText()
        self.settings["copilot_model"] = self.cop_model.currentText()
        self.settings["auto_analyze"] = self.auto_analyze_check.isChecked()

        # Purge any plaintext keys written by older versions
        for field in (*_SECRET_FIELDS, "api_key"):
            self.settings.pop(field, None)

        save_settings(self.settings)
        self.accept()
