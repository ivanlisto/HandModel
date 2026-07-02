from qgis.core import QgsLineSymbol, QgsRendererCategory, QgsCategorizedSymbolRenderer
from qgis.core import QgsRasterShader, QgsColorRampShader, QgsSingleBandPseudoColorRenderer
from osgeo import gdal
import numpy as np
from osgeo import gdal, ogr, osr
from qgis.core import QgsVectorLayer, QgsProject, QgsLineSymbol, QgsSingleSymbolRenderer
from collections import deque
from qgis.PyQt.QtWidgets import QProgressDialog, QMessageBox, QApplication
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsRasterShader, QgsColorRampShader, QgsSingleBandPseudoColorRenderer,
    QgsRasterLayer, QgsProject
)
from qgis.PyQt.QtGui import QColor

# Cálculo do HAND Raster a partir do DEM e drenagem


def calculate_hand(dem_path, ldd_path, drainage_path, threshold, output_file, task=None, iface=None):
    dem_ds = gdal.Open(dem_path)
    if dem_ds is None:
        if iface:
            QMessageBox.critical(iface.mainWindow(),
                                 "HAND Raster", "Error opening DEM.")
        return

    dem_band = dem_ds.GetRasterBand(1)
    dem_array = dem_band.ReadAsArray().astype(float)
    rows, cols = dem_array.shape
    nodata = dem_band.GetNoDataValue() or -9999

    # Carrega drenagem
    if drainage_path:
        drainage_ds = gdal.Open(drainage_path)
        drainage_band = drainage_ds.GetRasterBand(1)
        drainage_array = drainage_band.ReadAsArray().astype(int)
    else:
        drainage_array = (dem_array < np.percentile(dem_array, 5)).astype(int)

    # Criar barra de progresso
    progress = None
    if iface:
        progress = QProgressDialog(
            "Calculating HAND Raster...", "Cancel", 0, rows, iface.mainWindow())
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

    # Construção da referência de elevação
    if not np.any(drainage_array > 0):
        ref_elev = dem_array.copy()
    else:
        ref_elev = np.full_like(dem_array, np.nan)
        q = deque()
        for i in range(rows):
            for j in range(cols):
                if drainage_array[i, j] > 0 and dem_array[i, j] != nodata:
                    ref_elev[i, j] = dem_array[i, j]
                    q.append((i, j))
            if progress:
                progress.setValue(i)
                if progress.wasCanceled():
                    return

        directions = [(-1, 0), (1, 0), (0, -1), (0, 1),
                      (-1, -1), (-1, 1), (1, -1), (1, 1)]
        while q:
            ci, cj = q.popleft()
            for di, dj in directions:
                ni, nj = ci+di, cj+dj
                if 0 <= ni < rows and 0 <= nj < cols:
                    if np.isnan(ref_elev[ni, nj]) and dem_array[ni, nj] != nodata:
                        ref_elev[ni, nj] = ref_elev[ci, cj]
                        q.append((ni, nj))

        ref_elev[np.isnan(ref_elev)] = dem_array[np.isnan(ref_elev)]

    # Calcula HAND
    hand_array = dem_array - ref_elev
    hand_array[hand_array < 0] = 0
    hand_array[np.isnan(hand_array)] = nodata

    if np.all(hand_array == nodata):
        if iface:
            QMessageBox.critical(iface.mainWindow(), "HAND Raster",
                                 "Error: no valid pixels found. Check DEM and drainage.")
        return

    # Salva raster
    driver = gdal.GetDriverByName("GTiff")
    out_ds = driver.Create(output_file, cols, rows, 1, gdal.GDT_Float32)
    out_ds.SetGeoTransform(dem_ds.GetGeoTransform())
    out_ds.SetProjection(dem_ds.GetProjection())

    out_band = out_ds.GetRasterBand(1)
    out_band.WriteArray(hand_array)
    out_band.SetNoDataValue(nodata)
    out_band.FlushCache()
    out_band.ComputeStatistics(False)
    out_ds = None

    if progress:
        progress.setValue(rows)
        progress.close()


"""Aplica estilo graduado ao HAND Raster"""


def apply_hand_style(raster_layer):
    provider = raster_layer.dataProvider()
    stats = provider.bandStatistics(1)

    min_val = stats.minimumValue
    max_val = stats.maximumValue

    ramp = QgsColorRampShader()
    ramp.setColorRampType(QgsColorRampShader.Interpolated)
    ramp.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(min_val, QColor(0, 0, 255), "Baixo"),
        QgsColorRampShader.ColorRampItem(
            (min_val+max_val)/2, QColor(0, 255, 0), "Médio"),
        QgsColorRampShader.ColorRampItem(max_val, QColor(255, 0, 0), "Alto"),
    ])

    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)

    renderer = QgsSingleBandPseudoColorRenderer(provider, 1, shader)
    raster_layer.setRenderer(renderer)
    raster_layer.triggerRepaint()

# Geração de curvas de nível a partir do raster HAND


def calculate_hand_contour(dem_path, ldd_path, drainage_path, threshold,
                           hand_raster, contour_file, interval=1.0,
                           task=None, iface=None):

    src_ds = gdal.Open(hand_raster)
    if src_ds is None:
        if iface:
            QMessageBox.critical(
                iface.mainWindow(), "HAND Contour", "Error opening the HAND raster.")
        return

    band = src_ds.GetRasterBand(1)
    srs = osr.SpatialReference()
    srs.ImportFromWkt(src_ds.GetProjection())

    drv = ogr.GetDriverByName("ESRI Shapefile")
    dst_ds = drv.CreateDataSource(contour_file)
    dst_layer = dst_ds.CreateLayer("contour", srs, ogr.wkbLineString)
    field_defn = ogr.FieldDefn("ELEV", ogr.OFTReal)
    dst_layer.CreateField(field_defn)

    # Barra de progresso
    progress = None
    if iface:
        progress = QProgressDialog(
            "Generating HAND Contour...", "Cancel", 0, 100, iface.mainWindow())
        progress.setWindowTitle("Processing HAND Contour")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

    # Geração das curvas
    gdal.ContourGenerate(band, interval, 0, [], 0, 0, dst_layer, 0, 0)

    if progress:
        progress.setValue(100)
        progress.close()

    dst_ds = None
    src_ds = None

    # Carregar shapefile no QGIS com estilo automático
    if iface:
        layer = QgsVectorLayer(contour_file, "HAND Contour", "ogr")
        if layer.isValid():
            # Estilo automático: linhas azuis finas
            symbol = QgsLineSymbol.createSimple({
                'color': '0,0,255',
                'width': '0.5'
            })
            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)
            layer.triggerRepaint()

            QgsProject.instance().addMapLayer(layer)
            QMessageBox.information(iface.mainWindow(), "HAND Contour",
                                    f"Processing completed!\nFile saved in:\n{contour_file}")
        else:
            QMessageBox.critical(iface.mainWindow(), "HAND Contour",
                                 f"Error: The generated file could not be loaded..\nCheck if {contour_file} existe.")


""" Aplica estilo automático às curvas HAND"""


def apply_hand_contour_style(layer):
    categories = []

    # Definir cores para faixas de HAND
    color_map = {
        "0-5": QColor(0, 0, 255),       # Azul
        "5-10": QColor(0, 255, 255),    # Ciano
        "10-20": QColor(0, 255, 0),     # Verde
        "20-50": QColor(255, 255, 0),   # Amarelo
        "50+": QColor(255, 0, 0),       # Vermelho
    }

    for label, color in color_map.items():
        symbol = QgsLineSymbol.createSimple(
            {'color': color.name(), 'width': '0.8'})
        category = QgsRendererCategory(label, symbol, label)
        categories.append(category)

    # Usa o campo "ELEV" para categorizar
    renderer = QgsCategorizedSymbolRenderer("ELEV", categories)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


"""Gera rede de canais a partir do DEM usando um limiar simples."""


def generate_channels(dem_array, threshold=100, nodata=-9999):
    percentile = np.percentile(dem_array[dem_array != nodata], 5)
    channels = (dem_array <= percentile).astype(int)
    return channels


"""Calcula HAND automaticamente a partir de um DEM,gerando e salvando também o raster de canais."""


def calculate_hand_channel_auto(dem_path, hand_output, channels_output, threshold=100, nodata=-9999, iface=None):
    dem_ds = gdal.Open(dem_path)
    dem_array = dem_ds.GetRasterBand(1).ReadAsArray().astype(float)
    rows, cols = dem_array.shape

    # Criar barra de progresso
    progress = None
    if iface:
        progress = QProgressDialog(
            "Calculating HAND Channel...", "Cancel", 0, rows, iface.mainWindow())
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

    # Gerar canais automaticamente
    channel_array = generate_channels(dem_array, threshold, nodata)

    # Salvar raster de canais
    driver = gdal.GetDriverByName("GTiff")
    ch_ds = driver.Create(channels_output, cols, rows, 1, gdal.GDT_Int16)
    ch_ds.SetGeoTransform(dem_ds.GetGeoTransform())
    ch_ds.SetProjection(dem_ds.GetProjection())
    ch_band = ch_ds.GetRasterBand(1)
    ch_band.WriteArray(channel_array)
    ch_band.SetNoDataValue(nodata)
    ch_band.FlushCache()
    ch_ds = None

    # HAND
    ref_elev = np.full_like(dem_array, np.nan)
    q = deque()
    for i in range(rows):
        for j in range(cols):
            if channel_array[i, j] > 0 and dem_array[i, j] != nodata:
                ref_elev[i, j] = dem_array[i, j]
                q.append((i, j))
        if progress:
            progress.setValue(i)
            if progress.wasCanceled():
                return

    directions = [(-1, 0), (1, 0), (0, -1), (0, 1),
                  (-1, -1), (-1, 1), (1, -1), (1, 1)]
    while q:
        ci, cj = q.popleft()
        for di, dj in directions:
            ni, nj = ci+di, cj+dj
            if 0 <= ni < rows and 0 <= nj < cols:
                if np.isnan(ref_elev[ni, nj]) and dem_array[ni, nj] != nodata:
                    ref_elev[ni, nj] = ref_elev[ci, cj]
                    q.append((ni, nj))

    ref_elev[np.isnan(ref_elev)] = dem_array[np.isnan(ref_elev)]
    hand_array = dem_array - ref_elev
    hand_array[hand_array < 0] = 0
    hand_array[np.isnan(hand_array)] = nodata

    out_ds = driver.Create(hand_output, cols, rows, 1, gdal.GDT_Float32)
    out_ds.SetGeoTransform(dem_ds.GetGeoTransform())
    out_ds.SetProjection(dem_ds.GetProjection())
    out_band = out_ds.GetRasterBand(1)
    out_band.WriteArray(hand_array)
    out_band.SetNoDataValue(nodata)
    out_band.FlushCache()
    out_ds = None

    if progress:
        progress.setValue(rows)
        progress.close()


"""Aplica estilo gradiente ao raster HAND."""


def apply_hand_style(layer):
    fcn = QgsColorRampShader()
    fcn.setColorRampType(QgsColorRampShader.Interpolated)
    fcn.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(0, QColor(0, 0, 255), "0 m"),
        QgsColorRampShader.ColorRampItem(5, QColor(0, 255, 255), "5 m"),
        QgsColorRampShader.ColorRampItem(10, QColor(0, 255, 0), "10 m"),
        QgsColorRampShader.ColorRampItem(20, QColor(255, 255, 0), "20 m"),
        QgsColorRampShader.ColorRampItem(50, QColor(255, 0, 0), "50 m+"),
    ])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(fcn)
    renderer = QgsSingleBandPseudoColorRenderer(
        layer.dataProvider(), 1, shader)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


"""Aplica estilo binário ao raster de canais."""


def apply_channels_style(layer):
    fcn = QgsColorRampShader()
    fcn.setColorRampType(QgsColorRampShader.Discrete)
    fcn.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(
            0, QColor(200, 200, 200), "No channel"),
        QgsColorRampShader.ColorRampItem(1, QColor(0, 0, 255), "Channel"),
    ])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(fcn)
    renderer = QgsSingleBandPseudoColorRenderer(
        layer.dataProvider(), 1, shader)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


"""Aplica estilo categorizado às isolinhas do HAND Contour. Cada intervalo recebe uma cor diferente."""


def apply_hand_contour_style(layer):
    categories = []

    # Definir cores para faixas de HAND
    color_map = {
        "0-5": QColor(0, 0, 255),       # Azul
        "5-10": QColor(0, 255, 255),    # Ciano
        "10-20": QColor(0, 255, 0),     # Verde
        "20-50": QColor(255, 255, 0),   # Amarelo
        "50+": QColor(255, 0, 0),       # Vermelho
    }

    for label, color in color_map.items():
        symbol = QgsLineSymbol.createSimple(
            {'color': color.name(), 'width': '0.8'})
        category = QgsRendererCategory(label, symbol, label)
        categories.append(category)

    # Usa o campo "ELEV" (elevacao das isolinhas) para categorizar
    renderer = QgsCategorizedSymbolRenderer("ELEV", categories)
    layer.setRenderer(renderer)
    layer.triggerRepaint()
