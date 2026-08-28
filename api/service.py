from models.model_manager import ModelManager


class APIService:
    """
    Façade utilisée par l'API.

    Cette classe ne contient aucune logique ML.
    Elle délègue entièrement les opérations à ModelManager.
    """

    def __init__(self) -> None:
        self.models = ModelManager()

    def dataset_info(self):
        return self.models.dataset_info()

    def train(self, model_name: str):
        return self.models.train(model_name)

    def predict(
        self,
        model_name: str,
        features: dict,
    ):
        return self.models.predict(
            model_name,
            features,
        )

    def list_versions(
        self,
        model_name: str | None = None,
    ):
        return self.models.list_versions(
            model_name
        )