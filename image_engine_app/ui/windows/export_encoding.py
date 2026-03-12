"""Expert export encoding dialog with apply signal for active-asset export settings."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from engine.models import ChromaSubsampling, ExportFormat


@dataclass(frozen=True)
class ExportEncodingOptions:
    """Encoding options chosen in the expert dialog."""

    format: str
    quality: int
    compression_level: int
    chroma_subsampling: str
    strip_metadata: bool


class ExportEncodingDialog(QDialog):
    """Advanced export encoding window for expert controls."""

    apply_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Encoding (Expert)")
        self.resize(540, 380)

        self._format_combo = QComboBox(self)
        self._quality_spin = QSpinBox(self)
        self._compression_spin = QSpinBox(self)
        self._chroma_combo = QComboBox(self)
        self._strip_metadata = QCheckBox("Strip metadata", self)
        self._apply_btn = QPushButton("Apply to Current Asset", self)

        self._build_ui()

    def current_options(self) -> ExportEncodingOptions:
        """Return current dialog values as a plain options object."""

        return ExportEncodingOptions(
            format=str(self._format_combo.currentData() or ExportFormat.AUTO.value),
            quality=int(self._quality_spin.value()),
            compression_level=int(self._compression_spin.value()),
            chroma_subsampling=str(self._chroma_combo.currentData() or ChromaSubsampling.AUTO.value),
            strip_metadata=bool(self._strip_metadata.isChecked()),
        )

    def load_from_asset(self, asset: object) -> None:
        """Load export settings from an asset into the dialog controls."""

        settings = getattr(getattr(getattr(asset, "edit_state", None), "settings", None), "export", None)
        if settings is None:
            return

        format_value = str(getattr(getattr(settings, "format", None), "value", ExportFormat.AUTO.value) or ExportFormat.AUTO.value)
        quality = int(getattr(settings, "quality", 90))
        compression = int(getattr(settings, "compression_level", 6))
        chroma_value = str(
            getattr(getattr(settings, "chroma_subsampling", None), "value", ChromaSubsampling.AUTO.value)
            or ChromaSubsampling.AUTO.value
        )
        strip_metadata = bool(getattr(settings, "strip_metadata", True))

        self._set_combo_by_data(self._format_combo, format_value)
        self._quality_spin.setValue(max(1, min(100, quality)))
        self._compression_spin.setValue(max(0, min(9, compression)))
        self._set_combo_by_data(self._chroma_combo, chroma_value)
        self._strip_metadata.setChecked(strip_metadata)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        guide = QLabel(
            "Apply advanced format/encoding values to the active asset. "
            "Use this for final size tuning after visual edits."
        )
        guide.setWordWrap(True)
        layout.addWidget(guide)

        form = QFormLayout()

        self._format_combo.addItem("Auto", ExportFormat.AUTO.value)
        self._format_combo.addItem("PNG", ExportFormat.PNG.value)
        self._format_combo.addItem("JPEG", ExportFormat.JPG.value)
        self._format_combo.addItem("WebP", ExportFormat.WEBP.value)
        self._format_combo.addItem("GIF", ExportFormat.GIF.value)
        self._format_combo.addItem("ICO", ExportFormat.ICO.value)
        self._format_combo.addItem("TIFF", ExportFormat.TIFF.value)
        self._format_combo.addItem("BMP", ExportFormat.BMP.value)
        form.addRow("Format", self._format_combo)

        self._quality_spin.setRange(1, 100)
        self._quality_spin.setValue(90)
        self._quality_spin.setToolTip("Lossy quality (mainly JPEG/WEBP).")
        form.addRow("Quality", self._quality_spin)

        self._compression_spin.setRange(0, 9)
        self._compression_spin.setValue(6)
        self._compression_spin.setToolTip("Compression level for supported formats.")
        form.addRow("Compression", self._compression_spin)

        self._chroma_combo.addItem("Auto", ChromaSubsampling.AUTO.value)
        self._chroma_combo.addItem("4:4:4", ChromaSubsampling.CS_444.value)
        self._chroma_combo.addItem("4:2:2", ChromaSubsampling.CS_422.value)
        self._chroma_combo.addItem("4:2:0", ChromaSubsampling.CS_420.value)
        form.addRow("Chroma", self._chroma_combo)

        self._strip_metadata.setChecked(True)
        form.addRow("", self._strip_metadata)

        layout.addLayout(form)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self._apply_btn.clicked.connect(self._emit_apply_requested)
        footer.addWidget(self._apply_btn)
        footer.addWidget(QPushButton("Close", self, clicked=self.close))
        layout.addLayout(footer)

    def _emit_apply_requested(self) -> None:
        self.apply_requested.emit(self.current_options())

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str) -> None:
        for index in range(combo.count()):
            if str(combo.itemData(index)) == str(value):
                combo.setCurrentIndex(index)
                return
