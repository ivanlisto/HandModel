import os
from qgis.core import (
    QgsRasterLayer, QgsProject, QgsMapLayer,
    QgsRasterShader, QgsColorRampShader, QgsSingleBandPseudoColorRenderer
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFileDialog, QHBoxLayout, QMessageBox
)
from qgis.PyQt.QtCore import Qt
from PyQt5.QtGui import QColor
from qgis.PyQt.QtGui import QFont


def apply_quartile_style(raster_layer):
    """Aplica simbologia de quartis ao raster."""
    provider = raster_layer.dataProvider()
    stats = provider.bandStatistics(1)

    min_val = stats.minimumValue
    max_val = stats.maximumValue

    if min_val is None or max_val is None or min_val == max_val:
        return

    step = (max_val - min_val) / 4.0

    shader = QgsRasterShader()
    color_ramp = QgsColorRampShader()
    color_ramp.setColorRampType(QgsColorRampShader.Interpolated)

    items = [
        QgsColorRampShader.ColorRampItem(
            min_val, QColor("#00ff00"), "Q1 - Baixa"),
        QgsColorRampShader.ColorRampItem(
            min_val + step, QColor("#ffff00"), "Q2"),
        QgsColorRampShader.ColorRampItem(
            min_val + 2 * step, QColor("#ffa500"), "Q3"),
        QgsColorRampShader.ColorRampItem(
            max_val, QColor("#ff0000"), "Q4 - Alta"),
    ]
    color_ramp.setColorRampItemList(items)
    shader.setRasterShaderFunction(color_ramp)

    renderer = QgsSingleBandPseudoColorRenderer(provider, 1, shader)
    raster_layer.setRenderer(renderer)
    raster_layer.triggerRepaint()


class SlopeDialog(QDialog):
    def __init__(self, iface, parent=None, workspace="C:/PyQGIS/OutputHAND"):
        super().__init__(parent)
        self.iface = iface
        self.workspace = workspace
        self.dem_layer = None

        self.setWindowTitle("Slope")

        layout = QVBoxLayout()

        bold_font = QFont()
        bold_font.setBold(True)

        # Seleção do DEM (camadas do projeto)
        lbl_dem = QLabel("DEM File (from the project):")
        lbl_dem.setFont(bold_font)
        layout.addWidget(lbl_dem)

        self.combo_dem = QComboBox()
        raster_layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if lyr.type() == QgsMapLayer.RasterLayer and lyr.isValid()
        ]
        for lyr in raster_layers:
            self.combo_dem.addItem(lyr.name(), lyr.source())
        layout.addWidget(self.combo_dem)

        # Saída do slope
        lbl_out = QLabel("Output File:")
        lbl_out.setFont(bold_font)
        layout.addWidget(lbl_out)

        h_out = QHBoxLayout()
        self.out_line = QLineEdit()
        self.out_line.setText(os.path.join(self.workspace, "slope.tif"))
        btn_out = QPushButton("Save As…")
        btn_out.clicked.connect(self.selecionar_saida)
        h_out.addWidget(self.out_line)
        h_out.addWidget(btn_out)
        layout.addLayout(h_out)

        # Unidade de saída
        lbl_unit = QLabel("Output Unit:")
        lbl_unit.setFont(bold_font)
        layout.addWidget(lbl_unit)

        self.combo_unidade = QComboBox()
        self.combo_unidade.addItem("Degrees", False)
        self.combo_unidade.addItem("Percentage", True)
        layout.addWidget(self.combo_unidade)

        # Botões OK/Cancel lado a lado
        h_btns = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        h_btns.addWidget(btn_ok)
        h_btns.addWidget(btn_cancel)
        layout.addLayout(h_btns)

        self.setLayout(layout)

    def selecionar_saida(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Output", self.out_line.text(),
            "GeoTIFF (*.tif);;All files (*.*)"
        )
        if filename:
            if not filename.lower().endswith(".tif"):
                filename += ".tif"
            self.out_line.setText(filename)

    def getParameters(self):
        dem_path = self.combo_dem.currentData()
        dem_layer = QgsRasterLayer(
            dem_path, "DEM selected") if dem_path else None
        as_percent = self.combo_unidade.currentData()

        return {
            "output_name": os.path.splitext(os.path.basename(self.out_line.text()))[0],
            "layer": dem_layer,
            "as_percent": as_percent,
            "output_path": self.out_line.text()
        }
