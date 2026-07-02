import os
from qgis.core import QgsRasterLayer, QgsProject, QgsMapLayer
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFileDialog, QHBoxLayout, QDoubleSpinBox
)
from qgis.PyQt.QtGui import QFont


class DrainageDialog(QDialog):
    def __init__(self, iface, parent=None, workspace=None):
        super().__init__(parent)
        self.iface = iface
        self.workspace = workspace if workspace else os.getcwd()

        self.setWindowTitle("Drainage Network (GRASS)")

        layout = QVBoxLayout()
        bold_font = QFont()
        bold_font.setBold(True)

        # DEM
        lbl_dem = QLabel("DEM File (from project):")
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

        # Threshold
        lbl_th = QLabel("Threshold (limiar):")
        lbl_th.setFont(bold_font)
        layout.addWidget(lbl_th)

        # Unidade do threshold
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("Pixels", "pixels")
        self.unit_combo.addItem("Square meters (m²)", "m2")
        self.unit_combo.addItem("Hectares (ha)", "ha")
        self.unit_combo.addItem("Square kilometers (km²)", "km2")
        layout.addWidget(self.unit_combo)

        # Valor do threshold
        self.th_spin = QDoubleSpinBox()
        self.th_spin.setRange(0.0, 1000000.0)
        self.th_spin.setSingleStep(1.0)
        self.th_spin.setValue(1000.0)  # valor padrão
        layout.addWidget(self.th_spin)

        # Saída
        lbl_out = QLabel("Output File:")
        lbl_out.setFont(bold_font)
        layout.addWidget(lbl_out)

        h_out = QHBoxLayout()
        self.out_line = QLineEdit()
        self.out_line.setText(os.path.join(self.workspace, "drainage.tif"))
        btn_out = QPushButton("Save as…")
        btn_out.clicked.connect(self.selecionar_saida)
        h_out.addWidget(self.out_line)
        h_out.addWidget(btn_out)
        layout.addLayout(h_out)

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
            self, "Save output", self.out_line.text(),
            "GeoTIFF (*.tif);;All files (*.*)"
        )
        if filename:
            if not filename.lower().endswith(".tif"):
                filename += ".tif"
            self.out_line.setText(filename)

    def getParameters(self):
        dem_path = self.combo_dem.currentData()
        dem_layer = QgsRasterLayer(
            dem_path, "DEM Selected") if dem_path else None

        # Conversão do threshold para pixels
        threshold_value = self.th_spin.value()
        unit = self.unit_combo.currentData()

        threshold_pixels = None
        if dem_layer and dem_layer.isValid():
            res_x = dem_layer.rasterUnitsPerPixelX()
            res_y = dem_layer.rasterUnitsPerPixelY()
            pixel_area = res_x * res_y

            if unit == "pixels":
                threshold_pixels = int(threshold_value)
            elif unit == "m2":
                threshold_pixels = int(threshold_value / pixel_area)
            elif unit == "ha":
                threshold_pixels = int((threshold_value * 10000) / pixel_area)
            elif unit == "km2":
                threshold_pixels = int((threshold_value * 1e6) / pixel_area)

        return {
            "output_name": os.path.splitext(os.path.basename(self.out_line.text()))[0],
            "layer": dem_layer,
            "threshold": threshold_pixels,
            "output_path": self.out_line.text()
        }
