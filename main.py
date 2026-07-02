import os
import numpy as np
import processing
from qgis.core import (
    QgsRasterLayer, QgsVectorLayer, QgsProject,
    QgsMessageLog, Qgis, QgsApplication, QgsRasterBlock,
    QgsRasterFileWriter, QgsProcessingFeedback
)
from qgis.PyQt.QtWidgets import (
    QToolBar, QMenu, QToolButton, QFileDialog, QDialog, QComboBox, QLineEdit, QDoubleSpinBox,
    QVBoxLayout, QLabel, QSpinBox, QPushButton, QMessageBox, QProgressDialog, QAction
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt, QSettings

# Diálogos
from .hydrotools_provider import HydroToolsProvider
from .correct_dem_dialog import CorrectDemDialog
from .drainage_dialog import DrainageDialog
from .slope_dialog import SlopeDialog, apply_quartile_style
from .flowacc_dialog import FlowAccDialog
from .hand_processing import (
    calculate_hand, calculate_hand_contour, calculate_hand_channel_auto,
    apply_hand_style, apply_channels_style, apply_hand_contour_style
)
from .handmodel_dialog import HandModelDialog

# --------------------------------------------------
# PLUGIN PRINCIPAL
# --------------------------------------------------


class HandModelPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.toolbar = None
        self.tool_button = None
        self.menu = None
        self.tile_size = 100
        self.plugin_dir = os.path.dirname(__file__)
        self.settings = QSettings("HANDMODEL", "HandModelPlugin")
        self.provider = None

    # --------------------------------------------------
    # PROCESSING PROVIDER
    # --------------------------------------------------
    def initProcessing(self):
        if self.provider is None:
            self.provider = HydroToolsProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def unloadProcessing(self):
        try:
            if self.provider:
                if self.provider in QgsApplication.processingRegistry().providers():
                    QgsApplication.processingRegistry().removeProvider(self.provider)
                self.provider = None
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error unloading provider: {str(e)}", "Hand Model", Qgis.Warning)

    # --------------------------------------------------
    # INITGUI
    # --------------------------------------------------
    def initGui(self):
        self.initProcessing()

        self.toolbar = QToolBar("HandModel")
        self.toolbar.setObjectName("SisHandToolbar")
        self.toolbar.setWindowIcon(
            QIcon(os.path.join(self.plugin_dir, "icons", "hand.png")))
        self.iface.mainWindow().addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.tool_button = QToolButton()
        self.tool_button.setIcon(
            QIcon(os.path.join(self.plugin_dir, "icons", "icon.png")))
        self.tool_button.setPopupMode(QToolButton.InstantPopup)
        self.tool_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.tool_button.setToolTip(
            "HandModel - Height Above The Nearest Drainage")
        self.tool_button.setStatusTip(
            "Executes HAND routines (Raster, Channel, Contour)")

        self.menu = QMenu(self.iface.mainWindow())

        # Configurações
        self.menu.addAction(QIcon(os.path.join(self.plugin_dir, 'icons', 'workspace.png')),
                            "Set Workspace Directory", self.set_workspace).setToolTip("Definir pasta de trabalho")
        self.menu.addAction(QIcon(os.path.join(self.plugin_dir, 'icons', 'tile.png')),
                            "Set Tile Size", self.set_tile_size_dialog).setToolTip("Definir tamanho de tile")
        self.menu.addSeparator()

        # Rotinas de pré-processamento
        routines = [
            ("Corrected DEM -> LDD", "dem_corr.png",
             self.correct_dem, "Corrects DEM and generates LDD."),
            ("Flow Accumulation (ACC)", "flow_acc.png",
             self.flow_acc_grass, "Calculates flow accumulation."),
            ("Extract Drainage", "drainage.png",
             self.run_drainage, "Extracts the Drainage Network"),
            ("Slope (%)", "slope.png", self.slope, "Calculates Slope in %"),
        ]
        for text, icon_name, callback, tip in routines:
            icon = QIcon(os.path.join(self.plugin_dir, 'icons', icon_name))
            action = self.menu.addAction(icon, text, callback)
            action.setToolTip(tip)

        # Separador antes dos cálculos HAND
        self.menu.addSeparator()

        # Rotinas HAND
        hand_routines = [
            ("HAND Channel", "hchan.png", self.run_hand_channel,
             "Generates Channels and the HAND"),
            ("HAND Raster", "hand_raster.png",
             self.run_hand_raster, "Calculate Hand Raster"),
            ("HAND Contour", "hand_contour.png",
             self.run_hand_contour, "Generates contour lines in HAND."),
        ]
        for text, icon_name, callback, tip in hand_routines:
            icon = QIcon(os.path.join(self.plugin_dir, 'icons', icon_name))
            action = self.menu.addAction(icon, text, callback)
            action.setToolTip(tip)

        # Nova rotina de classificação HAND
        classify_icon = QIcon(os.path.join(
            self.plugin_dir, 'icons', 'classify.png'))
        action = self.menu.addAction(classify_icon,
                                     "HAND Classification",
                                     self.run_hand_classification)
        action.setToolTip(
            "Classify HAND Raster into Waterlogged, Ecotone, Slope, Plateau")

        self.tool_button.setMenu(self.menu)
        self.toolbar.addWidget(self.tool_button)

    def unload(self):
        self.unloadProcessing()
        if self.toolbar:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar = None
        if self.menu:
            self.menu.clear()
            self.menu = None

    # --------------------------------------------------
    # WORKSPACE
    # --------------------------------------------------
    def set_workspace(self):
        folder = QFileDialog.getExistingDirectory(self.iface.mainWindow(),
                                                  "Select Workspace",
                                                  self.get_workspace())
        if folder:
            self.settings.setValue("workspace", folder)
            self.iface.messageBar().pushMessage("Hand Model",
                                                f"Workspace configured for: {folder}",
                                                level=Qgis.Info)

    def get_workspace(self):
        return self.settings.value("workspace", self.plugin_dir)

    def output_file(self, name):
        workspace = self.get_workspace()
        if workspace:
            return os.path.join(workspace, f"{name}.tif")
        return "TEMPORARY_OUTPUT"

    # --------------------------------------------------
    # TILE SIZE
    # --------------------------------------------------

    def set_tile_size_dialog(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("Tile Size")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Tile size (pixels):"))

        spin = QSpinBox()
        spin.setRange(500, 5000)
        spin.setValue(self.tile_size)
        layout.addWidget(spin)

        btn = QPushButton("OK")
        btn.clicked.connect(lambda: self.save_tile_size(dialog, spin.value()))
        layout.addWidget(btn)

        dialog.exec_()

    def save_tile_size(self, dialog, value):
        self.tile_size = value
        dialog.accept()

    # --------------------------------------------------
    # ROTINA - DEM CORRIGIDO E LDD
    # --------------------------------------------------
    def correct_dem(self):
        try:
            dialog = CorrectDemDialog(self.iface.mainWindow(),
                                      self.get_workspace(),
                                      self.output_file("dem_corrected"),
                                      self.output_file("ldd"))
            dialog.exec_()
            self.iface.messageBar().pushMessage(
                "Hand Model", "DEM successfully corrected.!", level=Qgis.Success)
        except Exception as e:
            self.iface.messageBar().pushMessage(
                "Hand Model", f"Error correcting DEM: {str(e)}", level=Qgis.Critical)

    # --------------------------------------------------
    # ROTINA SLOPE (thread principal)
    # --------------------------------------------------
    def slope(self):
        try:
            dialog = SlopeDialog(self.iface, parent=self.iface.mainWindow())
            if not dialog.exec_():
                return

            params = dialog.getParameters()
            output_name = params["output_name"]
            dem_layer = params["layer"]
            as_percent = params["as_percent"]

            if not isinstance(dem_layer, QgsRasterLayer):
                self.iface.messageBar().pushMessage(
                    "Hand Model", "Select a valid DEM.", level=Qgis.Critical
                )
                return

            output_path = os.path.join(
                self.get_workspace(), f"{output_name}_Decliv.tif")

            # Executa direto, sem QProgressDialog
            resultado = processing.run("gdal:slope", {
                'INPUT': dem_layer.source(),
                'BAND': 1,
                'SCALE': 1.0,
                'AS_PERCENT': as_percent,
                'COMPUTE_EDGES': True,
                'ZEVENBERGEN': False,
                'OUTPUT': output_path
            })['OUTPUT']

            slope_layer = QgsRasterLayer(str(resultado), "Slope")
            if slope_layer.isValid():
                apply_quartile_style(slope_layer)
                QgsProject.instance().addMapLayer(slope_layer)
                self.iface.messageBar().pushMessage(
                    "Hand Model", f"Slope (Slope) generated successfully: {output_path}", level=Qgis.Success
                )
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "File Saved",
                    f"The file was saved in the workspace:\n{output_path}"
                )
            else:
                self.iface.messageBar().pushMessage(
                    "Hand Model", "File generated, but could not be loaded.", level=Qgis.Critical
                )

        except Exception as e:
            self.iface.messageBar().pushMessage(
                "Hand Model", f"Error in slope: {str(e)}", level=Qgis.Critical
            )

    # --------------------------------------------------
    # ROTINA FLOWACC
    # --------------------------------------------------
    def flow_acc_grass(self):
        try:
            dlg = FlowAccDialog(self.iface, workspace=self.get_workspace())
            if not dlg.exec_():
                return

            params = dlg.getParameters()
            dem_layer = params["layer"]
            output_path = params["output_path"]

            if not dem_layer or not dem_layer.isValid():
                self.iface.messageBar().pushMessage(
                    "Hand Model", "Select a valid DEM.", level=Qgis.Critical
                )
                return

            # Barra de progresso
            progress_dialog = QProgressDialog(
                "Executing Flow Accumulation...", "Cancel", 0, 100, self.iface.mainWindow())
            progress_dialog.setWindowTitle("Flow ACC Processing")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setAutoClose(False)
            progress_dialog.setAutoReset(False)
            progress_dialog.show()

            feedback = CustomFeedback(self.iface, progress_dialog)
            progress_dialog.canceled.connect(feedback.cancel)

            self.iface.messageBar().pushMessage(
                "Hand Model", "Starting Flow Accumulation calculation...", level=Qgis.Info
            )

            # Executa o GRASS r.watershed para gerar acúmulo de fluxo
            processing.run("grass7:r.watershed", {
                'elevation': dem_layer.source(),
                'threshold': 1000,
                'accumulation': output_path,
                'accumulation_format': 1
            }, feedback=feedback)

            progress_dialog.setValue(100)
            progress_dialog.close()

            # Carregar resultado no QGIS
            flow_layer = QgsRasterLayer(output_path, "Flow Accumulation")
            if flow_layer.isValid():
                QgsProject.instance().addMapLayer(flow_layer)
                self.iface.messageBar().pushMessage(
                    "Hand Model", "Flow Accumulation successfully generated.!",
                    level=Qgis.Success
                )
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "File Saved",
                    f"The file was saved in the workspace:\n{output_path}"
                )
            else:
                self.iface.messageBar().pushMessage(
                    "Hand Model", "File generated, but could not be loaded.",
                    level=Qgis.Critical
                )

        except Exception as e:
            progress_dialog.close()
            self.iface.messageBar().pushMessage(
                "Hand Model", f"Error in GRASS flow accumulation: {str(e)}",
                level=Qgis.Critical
            )

    # --------------------------------------------------
    # ROTINA - DRENAGEM
    # --------------------------------------------------
    def run_drainage(self):
        try:
            from .drainage_dialog import DrainageDialog
            dlg = DrainageDialog(self.iface, workspace=self.get_workspace())
            if not dlg.exec_():
                return

            params = dlg.getParameters()
            dem_layer = params["layer"]
            threshold = params["threshold"]
            output_path = params["output_path"]

            if not dem_layer or not dem_layer.isValid():
                self.iface.messageBar().pushMessage(
                    "Hand Model", "Select a valid DEM.", level=Qgis.Critical
                )
                return

            # Barra de progresso
            progress_dialog = QProgressDialog(
                "Executing Drainage Extraction...", "Cancel", 0, 100, self.iface.mainWindow())
            progress_dialog.setWindowTitle("Drainage Processing")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setAutoClose(False)
            progress_dialog.setAutoReset(False)
            progress_dialog.show()

            feedback = CustomFeedback(self.iface, progress_dialog)
            progress_dialog.canceled.connect(feedback.cancel)

            self.iface.messageBar().pushMessage(
                "Hand Model", "Initiating drainage extraction...", level=Qgis.Info
            )

            # Executa GRASS r.stream.extract
            processing.run("grass7:r.stream.extract", {
                'elevation': dem_layer.source(),
                'threshold': threshold,
                'stream_raster': output_path,
                'stream_vector': 'TEMPORARY_OUTPUT',
                'direction': 'TEMPORARY_OUTPUT'
            }, feedback=feedback)

            progress_dialog.setValue(100)
            progress_dialog.close()

            # Carregar resultado no QGIS
            layer = QgsRasterLayer(output_path, "Drainage Network")
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                self.iface.messageBar().pushMessage(
                    "Hand Model",
                    f"Drainage extracted with threshold {threshold}.\nFile saved at: {output_path}",
                    level=Qgis.Success
                )
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "File Saved",
                    f"The file was saved in the workspace:\n{output_path}"
                )
            else:
                self.iface.messageBar().pushMessage(
                    "Hand Model", "File generated, but could not be loaded.",
                    level=Qgis.Critical
                )

        except Exception as e:
            progress_dialog.close()
            self.iface.messageBar().pushMessage(
                "Hand Model", f"Error in drainage extraction: {str(e)}",
                level=Qgis.Critical
            )

    # --------------------------------------------------
    # LDD - Auto Correct
    # --------------------------------------------------
    def auto_correct_ldd(self, ldd_path):
        layer = QgsRasterLayer(ldd_path, "LDD")
        if not layer.isValid():
            self.iface.messageBar().pushMessage(
                "Hand Model", "Error loading LDD.", level=Qgis.Critical)
            return None

        provider = layer.dataProvider()
        band = 1
        block = provider.block(band, layer.extent(),
                               layer.width(), layer.height())

        # Converter para NumPy
        arr = np.array([block.value(x, y) for y in range(
            block.height()) for x in range(block.width())])
        arr = arr.reshape((block.height(), block.width()))

        # Correção definitiva
        arr_corrected = np.where(arr < 0, -arr, arr)
        arr_corrected = np.where((arr_corrected >= 0) & (
            arr_corrected <= 8), arr_corrected, 0)

        output_path = self.output_file("ldd_corrected")

        corrected_block = QgsRasterBlock(
            provider.dataType(band), block.width(), block.height())
        for y in range(block.height()):
            for x in range(block.width()):
                corrected_block.setValue(x, y, float(arr_corrected[y, x]))

        writer = QgsRasterFileWriter(output_path)
        writer.setCreateOptions(["COMPRESS=LZW"])
        writer.writeRaster(corrected_block, block.width(), block.height(),
                           layer.extent(), provider.crs())

        self.iface.messageBar().pushMessage(
            "Hand Model", "Corrected LDD saved successfully!", level=Qgis.Success)

        return output_path

    # --------------------------------------------------
    # HAND Raster
    # --------------------------------------------------
    def run_hand_raster(self):
        # Obter camadas raster carregadas no projeto
        layers = [layer for layer in QgsProject.instance().mapLayers().values()
                  if isinstance(layer, QgsRasterLayer)]
        if not layers:
            QMessageBox.warning(self.iface.mainWindow(), "HAND Raster",
                                "No raster layers loaded in the project.")
            return

        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("HAND Raster")

        layout = QVBoxLayout(dialog)

        # Seleção do DEM
        layout.addWidget(QLabel("Choose the DEM:"))
        combo_dem = QComboBox()
        for layer in layers:
            combo_dem.addItem(layer.name(), layer)
        layout.addWidget(combo_dem)

        # Seleção do LDD
        layout.addWidget(QLabel("Choose the LDD:"))
        combo_ldd = QComboBox()
        for layer in layers:
            combo_ldd.addItem(layer.name(), layer)
        layout.addWidget(combo_ldd)

        # Seleção da drenagem
        layout.addWidget(QLabel("Choose the Drainage:"))
        combo_drain = QComboBox()
        for layer in layers:
            combo_drain.addItem(layer.name(), layer)
        layout.addWidget(combo_drain)

        # Nome do arquivo de saída
        layout.addWidget(QLabel("Output file name (without extension):"))
        output_edit = QLineEdit()
        output_edit.setText("hand_raster")
        layout.addWidget(output_edit)

        # Threshold
        layout.addWidget(QLabel("Accumulation threshold:"))

        # Unidade do threshold
        unit_combo = QComboBox()
        unit_combo.addItem("Pixels", "pixels")
        unit_combo.addItem("Square meters (m²)", "m2")
        unit_combo.addItem("Hectares (ha)", "ha")
        unit_combo.addItem("Square kilometers (km²)", "km2")
        layout.addWidget(unit_combo)

        # Valor do threshold
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1000000.0)
        spin.setSingleStep(1.0)
        spin.setValue(100.0)
        layout.addWidget(spin)

        # Botão OK
        btn = QPushButton("Execute")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)

        if not dialog.exec_():
            return

        dem_layer = combo_dem.currentData()
        ldd_layer = combo_ldd.currentData()
        drain_layer = combo_drain.currentData()

        # Verificar se são rasters válidos
        if not (dem_layer and dem_layer.isValid()):
            QMessageBox.critical(self.iface.mainWindow(),
                                 "HAND Raster", "Invalid DEM.")
            return
        if not (ldd_layer and ldd_layer.isValid()):
            QMessageBox.critical(self.iface.mainWindow(),
                                 "HAND Raster", "Invalid LDD.")
            return
        if not (drain_layer and drain_layer.isValid()):
            QMessageBox.critical(self.iface.mainWindow(),
                                 "HAND Raster", "Invalid Drainage.")
            return

        dem_path = dem_layer.source()
        ldd_path = ldd_layer.source()
        drainage_path = drain_layer.source()
        output_name = output_edit.text().strip()

        # Conversão do threshold para pixels
        threshold_value = spin.value()
        unit = unit_combo.currentData()

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

        output_file = os.path.join(self.get_workspace(), f"{output_name}.tif")

        try:
            # Barra de progresso
            progress_dialog = QProgressDialog(
                "Executing HAND Raster...", "Cancel", 0, 100, self.iface.mainWindow())
            progress_dialog.setWindowTitle("Processing HAND Raster")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setAutoClose(True)
            progress_dialog.setAutoReset(True)
            progress_dialog.show()

            feedback = CustomFeedback(self.iface, progress_dialog)
            progress_dialog.canceled.connect(feedback.cancel)

            self.iface.messageBar().pushMessage(
                "Hand Model", "Starting HAND Raster calculation...", level=Qgis.Info
            )

            # Passa o threshold convertido para pixels
            calculate_hand(dem_path, ldd_path, drainage_path,
                           threshold_pixels, output_file, task=None, iface=self.iface)

            progress_dialog.setValue(100)
            progress_dialog.close()

            # Carregar resultado no QGIS
            layer = QgsRasterLayer(output_file, "HAND Raster")
            if layer.isValid():
                apply_hand_style(layer)
                QgsProject.instance().addMapLayer(layer)
                self.iface.messageBar().pushMessage(
                    "Hand Model",
                    f"HAND Raster generated successfully!\nFile saved at: {output_file}",
                    level=Qgis.Success
                )
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "File Saved",
                    f"The file was saved in the workspace:\n{output_file}"
                )
            else:
                self.iface.messageBar().pushMessage(
                    "Hand Model", "File generated, but could not be loaded.",
                    level=Qgis.Critical
                )

        except Exception as e:
            progress_dialog.close()
            QMessageBox.critical(self.iface.mainWindow(), "HAND Raster",
                                 f"Error during processing: {str(e)}")

    # --------------------------------------------------
    # HAND Contour
    # --------------------------------------------------
    def run_hand_contour(self):
        # Obter camadas raster carregadas no projeto
        layers = [layer for layer in QgsProject.instance().mapLayers().values()
                  if isinstance(layer, QgsRasterLayer)]
        if not layers:
            QMessageBox.warning(self.iface.mainWindow(),
                                "HAND Contour", "No raster layers loaded in the project.")
            return

        # Criar diálogo customizado
        from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QLineEdit, QSpinBox, QPushButton
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("HAND Contour")

        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Choose the HAND raster:"))
        combo = QComboBox()
        for layer in layers:
            combo.addItem(layer.name(), layer)
        layout.addWidget(combo)

        layout.addWidget(QLabel("Output file name (without extension):"))
        output_edit = QLineEdit()
        output_edit.setText("hand_contour")
        layout.addWidget(output_edit)

        layout.addWidget(QLabel("Interval of contour lines (meters):"))
        spin = QSpinBox()
        spin.setRange(1, 1000)
        spin.setValue(5)
        layout.addWidget(spin)

        btn = QPushButton("Execute")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)

        if not dialog.exec_():
            return

        hand_layer = combo.currentData()
        hand_raster = hand_layer.source()
        output_name = output_edit.text().strip()
        interval = spin.value()

        contour_file = os.path.join(self.get_workspace(), f"{output_name}.shp")

        try:
            self.iface.messageBar().pushMessage(
                "Hand Model", "Starting HAND contour calculation...", level=Qgis.Info
            )

            from .hand_processing import calculate_hand_contour, apply_hand_contour_style

            # Executa cálculo das isolinhas
            calculate_hand_contour(
                None, None, None, 0, hand_raster, contour_file, interval, task=None, iface=self.iface)

            # Carregar vetor no QGIS
            layer = QgsVectorLayer(
                contour_file, "HAND Contour (Isolinhas)", "ogr")
            if layer.isValid():
                apply_hand_contour_style(layer)
                QgsProject.instance().addMapLayer(layer)   # apenas aqui
                self.iface.messageBar().pushMessage(
                    "Hand Model",
                    f"HAND Contour generated successfully!\nFile saved at: {contour_file}",
                    level=Qgis.Success
                )
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "File Saved",
                    f"The file was saved in the workspace:\n{contour_file}"
                )
            else:
                self.iface.messageBar().pushMessage(
                    "Hand Model", "File generated, but could not be loaded.",
                    level=Qgis.Critical
                )

        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "HAND Contour",
                                 f"Error during processing: {str(e)}")

    # --------------------------------------------------
    # HAND Channel
    # --------------------------------------------------
    def run_hand_channel(self):
        # Obter camadas raster carregadas no projeto
        layers = [layer for layer in QgsProject.instance().mapLayers().values()
                  if isinstance(layer, QgsRasterLayer)]
        if not layers:
            QMessageBox.warning(self.iface.mainWindow(),
                                "HAND Channel", "No raster layers loaded in the project.")
            return

        # Criar diálogo customizado
        from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QLineEdit, QDoubleSpinBox, QPushButton
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("HAND Channel")

        layout = QVBoxLayout(dialog)

        # Seleção do DEM
        layout.addWidget(QLabel("Choose the DEM:"))
        combo = QComboBox()
        for layer in layers:
            combo.addItem(layer.name(), layer)
        layout.addWidget(combo)

        # Nome do arquivo de saída
        layout.addWidget(QLabel("Output file name (without extension):"))
        output_edit = QLineEdit()
        output_edit.setText("hand_channel")
        layout.addWidget(output_edit)

        # Threshold
        layout.addWidget(QLabel("Accumulation threshold:"))

        # Unidade do threshold
        unit_combo = QComboBox()
        unit_combo.addItem("Pixels", "pixels")
        unit_combo.addItem("Square meters (m²)", "m2")
        unit_combo.addItem("Hectares (ha)", "ha")
        unit_combo.addItem("Square kilometers (km²)", "km2")
        layout.addWidget(unit_combo)

        # Valor do threshold
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1000000.0)
        spin.setSingleStep(1.0)
        spin.setValue(100.0)
        layout.addWidget(spin)

        # Botão OK
        btn = QPushButton("Execute")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)

        if not dialog.exec_():
            return

        dem_layer = combo.currentData()
        if not dem_layer or not dem_layer.isValid():
            QMessageBox.critical(self.iface.mainWindow(),
                                 "HAND Channel", "Invalid DEM.")
            return

        dem_path = dem_layer.source()
        output_name = output_edit.text().strip()

        # Conversão do threshold para pixels
        threshold_value = spin.value()
        unit = unit_combo.currentData()

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

        # Caminhos de saída no workspace
        hand_output = os.path.join(self.get_workspace(), f"{output_name}.tif")
        channels_output = os.path.join(
            self.get_workspace(), f"{output_name}_channels.tif")

        try:
            # Barra de progresso
            progress_dialog = QProgressDialog(
                "Executing HAND Channel...", "Cancel", 0, 100, self.iface.mainWindow())
            progress_dialog.setWindowTitle("HAND Channel Processing")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setAutoClose(True)
            progress_dialog.setAutoReset(True)
            progress_dialog.show()

            feedback = CustomFeedback(self.iface, progress_dialog)
            progress_dialog.canceled.connect(feedback.cancel)

            self.iface.messageBar().pushMessage(
                "Hand Model", "Starting HAND Channel calculation...", level=Qgis.Info
            )

            # Chama a função de processamento com threshold convertido
            calculate_hand_channel_auto(
                dem_path, hand_output, channels_output, threshold=threshold_pixels)

            progress_dialog.setValue(100)
            progress_dialog.close()

            # Carregar camadas resultantes
            hand_layer = QgsRasterLayer(hand_output, "HAND Channel")
            channels_layer = QgsRasterLayer(
                channels_output, "Canais Detectados")

            if hand_layer.isValid():
                apply_hand_style(hand_layer)
                QgsProject.instance().addMapLayer(hand_layer)

            if channels_layer.isValid():
                apply_channels_style(channels_layer)
                QgsProject.instance().addMapLayer(channels_layer)

            self.iface.messageBar().pushMessage(
                "Hand Model",
                f"HAND Channel completed!\nHAND saved at: {hand_output}\n"
                f"Channels saved at: {channels_output}\nThreshold used: {threshold_pixels} (pixels)",
                level=Qgis.Success
            )
            QMessageBox.information(
                self.iface.mainWindow(),
                "HAND Channel",
                f"Processing completed!\nHAND saved at:\n{hand_output}\n"
                f"Channels saved at:\n{channels_output}\nThreshold used: {threshold_pixels} (pixels)"
            )

        except Exception as e:
            progress_dialog.close()
            QMessageBox.critical(self.iface.mainWindow(), "HAND Channel",
                                 f"Error during processing: {str(e)}")

    # --------------------------------------------------
    # HAND CLASSIFICATION
    # --------------------------------------------------
    def run_hand_classification(self):
        dlg = HandModelDialog(self.iface, self, self.iface.mainWindow())
        dlg.exec_()


# --------------------------------------------------
# FEEDBACK ÚNICO
# --------------------------------------------------


class CustomFeedback(QgsProcessingFeedback):
    def __init__(self, iface, progress_dialog=None):
        super().__init__()
        self.iface = iface
        self.progress_dialog = progress_dialog
        self.is_canceled = False

    def setProgress(self, progress):
        if self.progress_dialog:
            self.progress_dialog.setValue(int(progress))

    def cancel(self):
        self.is_canceled = True
        super().cancel()

    def isCanceled(self):
        return self.is_canceled
