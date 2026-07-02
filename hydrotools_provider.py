from qgis.core import QgsProcessingProvider


class HydroToolsProvider(QgsProcessingProvider):
    def __init__(self):
        super().__init__()

    def loadAlgorithms(self):
        # Nenhum algoritmo customizado aqui,
        # já que todos os cálculos são feitos direto no main.py
        pass

    def id(self):
        return 'hydrotools'

    def name(self):
        return 'Hydrological Tools'

    def longName(self):
        return self.name()
