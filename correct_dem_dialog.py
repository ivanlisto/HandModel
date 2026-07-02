import os
import tempfile
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QMessageBox,
    QFileDialog, QSpinBox, QDoubleSpinBox, QLineEdit, QHBoxLayout, QProgressDialog
)
from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.core import QgsRasterLayer, QgsProject, QgsProcessingFeedback, QgsProcessingContext
import processing


class CorrectDemDialog(QDialog):
    def __init__(self, parent=None, workspace=None, output_dem=None, output_ldd=None):
        super().__init__(parent)
        self.setWindowTitle("Correction of DEM")
        self.setMinimumWidth(400)
        self.workspace = workspace
        self.output_dem = output_dem
        self.output_ldd = output_ldd
        self.dem_layer = None

        layout = QVBoxLayout()

        # Seleção de camada raster
        layout.addWidget(QLabel("<b>Select a raster layer from the map:</b>"))
        self.dem_combo = QComboBox()
        self.dem_combo.addItem("Select a raster layer from the map...")
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == layer.RasterLayer:
                self.dem_combo.addItem(layer.name(), layer)
        layout.addWidget(self.dem_combo)

        # Seleção de arquivo raster
        layout.addWidget(
            QLabel("<b>Or choose a raster file from the disk:</b>"))
        self.btn_open = QPushButton("Open file...")
        self.btn_open.clicked.connect(self.selecionar_arquivo)
        layout.addWidget(self.btn_open)

        # Algoritmo
        layout.addWidget(QLabel("<b>Select the algorithm:</b>"))
        self.alg_combo = QComboBox()
        self.alg_combo.addItem("Fill No Data (native)", "native:fillnodata")
        self.alg_combo.addItem("Fill Gaps (SAGA)", "saga:fillgaps")
        layout.addWidget(self.alg_combo)

        # Parâmetros
        layout.addWidget(QLabel("<b>Parameters:</b>"))
        self.distance_spin = QSpinBox()
        self.distance_spin.setRange(1, 1000)
        self.distance_spin.setValue(10)
        layout.addWidget(QLabel("Distance (Fill No Data):"))
        layout.addWidget(self.distance_spin)

        # Unidade do threshold
        layout.addWidget(QLabel("<b>Threshold accumulation unit:</b>"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("Pixels", "pixels")
        self.unit_combo.addItem("Square meters (m²)", "m2")
        self.unit_combo.addItem("Hectares (ha)", "ha")
        self.unit_combo.addItem("Square kilometers (km²)", "km2")
        layout.addWidget(self.unit_combo)

        # Valor do threshold
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1000000.0)
        self.threshold_spin.setSingleStep(1.0)
        self.threshold_spin.setValue(100.0)
        layout.addWidget(QLabel("Threshold value:"))
        layout.addWidget(self.threshold_spin)

        # Campo para saída do DEM corrigido
        layout.addWidget(QLabel("<b>Output file for the corrected DEM:</b>"))
        dem_layout = QHBoxLayout()
        self.dem_line = QLineEdit(self.output_dem if self.output_dem else os.path.join(
            self.workspace, "dem_corrigido.tif"))
        btn_dem = QPushButton("Save as...")
        btn_dem.clicked.connect(self.selecionar_saida_dem)
        dem_layout.addWidget(self.dem_line)
        dem_layout.addWidget(btn_dem)
        layout.addLayout(dem_layout)

        # Campo para saída do LDD
        layout.addWidget(QLabel("<b>Output file for the LDD:</b>"))
        ldd_layout = QHBoxLayout()
        self.ldd_line = QLineEdit(
            self.output_ldd if self.output_ldd else os.path.join(self.workspace, "ldd.tif"))
        btn_ldd = QPushButton("Save as...")
        btn_ldd.clicked.connect(self.selecionar_saida_ldd)
        ldd_layout.addWidget(self.ldd_line)
        ldd_layout.addWidget(btn_ldd)
        layout.addLayout(ldd_layout)

        # Botão único
        btn_corrigir = QPushButton("Correct DEM and generate LDD")
        btn_corrigir.clicked.connect(self.executar_correcao)
        layout.addWidget(btn_corrigir)

        self.setLayout(layout)

    def selecionar_arquivo(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select the DEM", "",
            "Raster files (*.tif *.img *.asc *.vrt);;All files (*.*)"
        )
        if filename:
            self.dem_layer = QgsRasterLayer(filename, "DEM from the Disc")
            if self.dem_layer.isValid():
                QgsProject.instance().addMapLayer(self.dem_layer)
                QMessageBox.information(
                    self, "File selected", f"Raster loaded:\n{filename}")
            else:
                self.show_error("Invalid file or not a raster.")

    def selecionar_saida_dem(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save corrected DEM", self.dem_line.text(),
            "GeoTIFF (*.tif);;All files (*.*)"
        )
        if filename:
            if not filename.lower().endswith(".tif"):
                filename += ".tif"
            self.dem_line.setText(filename)

    def selecionar_saida_ldd(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save LDD", self.ldd_line.text(),
            "GeoTIFF (*.tif);;All files (*.*)"
        )
        if filename:
            if not filename.lower().endswith(".tif"):
                filename += ".tif"
            self.ldd_line.setText(filename)

    def executar_correcao(self):
        index = self.dem_combo.currentIndex()
        if index > 0:
            self.dem_layer = self.dem_combo.itemData(index)

        if not self.dem_layer:
            self.show_error("No layer selected.")
            return

        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        algoritmo = self.alg_combo.currentData()

        try:
            dem_path = self.dem_line.text().strip()
            if not dem_path.lower().endswith(".tif"):
                dem_path += ".tif"

            ldd_path = self.ldd_line.text().strip()
            if not ldd_path.lower().endswith(".tif"):
                ldd_path += ".tif"

            # Barra de progresso
            progress = QProgressDialog(
                "Processando DEM e LDD...", "Cancelar", 0, 100, self)
            progress.setWindowTitle("Processing DEM --> LDD")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.show()

            # Correção do DEM
            progress.setLabelText("Correcting DEM...")
            progress.setValue(20)
            QCoreApplication.processEvents()
            if algoritmo == "native:fillnodata":
                resultado = processing.run("native:fillnodata", {
                    'INPUT': self.dem_layer,
                    'BAND': 1,
                    'DISTANCE': self.distance_spin.value(),
                    'ITERATIONS': 1,
                    'NO_DATA': None,
                    'OUTPUT': dem_path
                }, feedback=feedback)['OUTPUT']
            elif algoritmo == "saga:fillgaps":
                resultado = processing.run("saga:fillgaps", {
                    'INPUT': self.dem_layer,
                    'TYPE': 0,
                    'THRESHOLD': self.threshold_spin.value(),
                    'RESULT': dem_path
                }, feedback=feedback)['RESULT']

            camada_corrigida = QgsRasterLayer(resultado, "DEM Corrected")
            QgsProject.instance().addMapLayer(camada_corrigida)

            # Conversão do threshold para pixels
            provider = self.dem_layer.dataProvider()
            res_x = self.dem_layer.rasterUnitsPerPixelX()
            res_y = self.dem_layer.rasterUnitsPerPixelY()
            pixel_area = res_x * res_y

            threshold_value = self.threshold_spin.value()
            unit = self.unit_combo.currentData()

            if unit == "pixels":
                threshold_pixels = int(threshold_value)
            elif unit == "m2":
                threshold_pixels = int(threshold_value / pixel_area)
            elif unit == "ha":
                threshold_pixels = int((threshold_value * 10000) / pixel_area)
            elif unit == "km2":
                threshold_pixels = int((threshold_value * 1e6) / pixel_area)

            # Cálculo do LDD
            progress.setLabelText("Calculating LDD...")
            progress.setValue(70)
            QCoreApplication.processEvents()

            ldd_result = processing.run("grass7:r.watershed", {
                'elevation': resultado,
                'threshold': threshold_pixels,
                'drainage': ldd_path,
                'GRASS_REGION_CELLSIZE_PARAMETER': 0,
                'GRASS_OUTPUT_TYPE_PARAMETER': 0
            }, context=context, feedback=feedback)['drainage']

            # Reclassificação
            reclass_table = """\
            -8 = 8
            -7 = 7
            -6 = 6
            -5 = 5
            -4 = 4
            -3 = 3
            -2 = 2
            -1 = 1
            0 = 0
            1 = 1
            2 = 2
            3 = 3
            4 = 4
            5 = 5
            6 = 6
            7 = 7
            8 = 8
            end
            """
            tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            tmpfile.write(reclass_table.encode("utf-8"))
            tmpfile.close()

            # Reclassificação com GRASS
            ldd_reclass = processing.run("grass7:r.reclass", {
                'input': ldd_result,
                'rules': tmpfile.name,
                'output': ldd_path + "_reclass.tif"
            }, context=context, feedback=feedback)['output']

            # Carregar camada reclassificada
            camada_ldd = QgsRasterLayer(ldd_reclass, "LDD Reclassified")
            if camada_ldd.isValid():
                QgsProject.instance().addMapLayer(camada_ldd)
            else:
                self.show_error("Error loading reclassified LDD.")

            progress.setLabelText("Finishing...")
            progress.setValue(100)
            QCoreApplication.processEvents()

            QMessageBox.information(
                self,
                "Success",
                f"DEM corrected and LDD calculated.\nOutputs:\n{dem_path}\n{ldd_path}_reclass.tif"
            )
            self.accept()

        except Exception as e:
            self.show_error(f"Error processing: {str(e)}")

    def show_error(self, mensagem):
        QMessageBox.critical(self, "Error", mensagem)
