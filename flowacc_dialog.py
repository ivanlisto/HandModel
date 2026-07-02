import os
from qgis.core import QgsRasterLayer, QgsProject, QgsMapLayer
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFileDialog, QHBoxLayout
)
from qgis.PyQt.QtGui import QFont


class FlowAccDialog(QDialog):
    def __init__(self, iface, parent=None, workspace=None):
        super().__init__(parent)
        self.iface = iface
        # workspace vem do main.py
        self.workspace = workspace if workspace else os.getcwd()

        self.setWindowTitle("ACC - Flow Accumulation (GRASS)")

        layout = QVBoxLayout()
        bold_font = QFont()
        bold_font.setBold(True)

        # DEM
        lbl_dem = QLabel("Correct DEM file (from the project):")
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

        # Saída
        lbl_out = QLabel("Output file:")
        lbl_out.setFont(bold_font)
        layout.addWidget(lbl_out)

        h_out = QHBoxLayout()
        self.out_line = QLineEdit()
        self.out_line.setText(os.path.join(
            self.workspace, "flow_accumulation.tif"))
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
            dem_path, "Correct DEM") if dem_path else None

        return {
            "output_name": os.path.splitext(os.path.basename(self.out_line.text()))[0],
            "layer": dem_layer,
            "output_path": self.out_line.text()
        }
