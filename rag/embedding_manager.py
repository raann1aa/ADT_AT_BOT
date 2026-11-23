import os
import re
from typing import List, Optional, Union, Dict, Any
import numpy as np

try:
    from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
except ImportError:
    EmbeddingFunction = object  # type: ignore
    Documents = List[str]       # type: ignore
    Embeddings = List[List[float]] # type: ignore

# Comprehensive dictionary for agricultural transliterations, Devanagari terms, and domain concepts
AGRI_SYNONYMS = {
    # Hinglish Crop names
    "gehu": "wheat wheat cultivation गेहूं",
    "dhan": "rice paddy cultivation धान",
    "chawal": "rice paddy धान",
    "kapas": "cotton cultivation कपास",
    "ganna": "sugarcane cultivation गन्ना",
    "pyaj": "onion cultivation storage rot प्याज",
    "kanda": "onion cultivation प्याज",
    "tamatar": "tomato cultivation टमाटर",
    "chana": "gram chickpea cultivation चना",
    "sarson": "mustard cultivation सरसों",
    "aalu": "potato cultivation आलू",
    "alu": "potato cultivation आलू",
    "mirch": "chilli cultivation leaf curl मिर्च",
    "makka": "maize corn cultivation मक्का",
    "makai": "maize corn cultivation मक्का",
    "soyabean": "soybean cultivation सोयाबीन",
    "soybean": "soybean cultivation सोयाबीन",

    # Pests and Diseases (Hinglish)
    "gulabi sundi": "pink bollworm cotton square larva rosette flower",
    "patta marod": "chilli leaf curl thrips mites",
    "churda murda": "chilli leaf curl thrips mites boat shaped",
    "murda": "chilli leaf curl thrips mites",
    "kanda sadi": "onion storage rot purple blotch curing chawl",
    "peela ratua": "yellow rust stripe rust wheat propiconazole",
    "ratua": "yellow rust stripe rust wheat",
    "safed gobh": "yellow stem borer rice dead heart whitehead",
    "safed balian": "yellow stem borer rice white earhead",
    "gardan tod": "rice neck blast magnaporthe tricyclazole",
    "fal fatna": "tomato blossom end rot calcium deficiency fruit cracking",
    "chepa": "mustard aphids sucking pest rogor",
    "maho": "mustard aphids sucking pest",
    "safed makkhi": "whitefly sucking pest cotton leaf curl",
    "sundi": "caterpillar borer larva",
    "keeda": "pest insect larva",
    "dawai": "spray medicine pesticide fungicide",
    "khad": "fertilizer urea DAP NPK manure",
    "paani": "irrigation water watering sinchai",
    "sinchai": "irrigation watering",
    "mitti": "soil testing health card",

    # Schemes (Hinglish)
    "pm kisan": "PM-KISAN Samman Nidhi 6000 installment eKYC land seeding beneficiary",
    "pmkisan": "PM-KISAN Samman Nidhi 6000 installment eKYC land seeding",
    "fasal bima": "PM Fasal Bima Yojana PMFBY crop insurance 72 hours claim localized calamity",
    "kcc": "Kisan Credit Card crop loan 4 percent interest subvention scale of finance",
    "kisan credit": "Kisan Credit Card crop loan 4 percent interest subvention",
    "mitti janch": "Soil Health Card scheme 12 parameters sampling",
    "kusum": "PM-KUSUM solar pump subsidy component B 60 percent",
    "solar pump": "PM-KUSUM solar pump agriculture subsidy",
    "drip subsidy": "Per Drop More Crop micro irrigation drip sprinkler subsidy 55 percent",

    # Devanagari Hindi Terms -> English/Hinglish Concepts (Crucial for MiniLM!)
    "गेहूं": "wheat gehu crop cultivation",
    "पीला रतुआ": "yellow rust stripe rust wheat puccinia propiconazole",
    "रतुआ": "yellow rust stripe rust wheat",
    "पीली पत्तियां": "yellow rust yellow leaves nitrogen deficiency chlorosis",
    "धान": "rice paddy dhan stem borer blast tricyclazole",
    "कपास": "cotton kapas pink bollworm square",
    "गुलाबी सुंडी": "pink bollworm cotton larva rosette",
    "गन्ना": "sugarcane ganna ratoon",
    "प्याज": "onion pyaj bulb storage rot purple blotch",
    "टमाटर": "tomato tamatar blossom end rot calcium late blight",
    "मिर्च": "chilli mirch leaf curl thrips mites",
    "पत्ता मरोड़": "chilli leaf curl thrips mites virus",
    "मक्का": "maize corn makka fall armyworm whorl",
    "चना": "gram chickpea chana wilt pod borer",
    "सरसों": "mustard sarson aphids chepa sulphur",
    "आलू": "potato aalu tuber late blight earthing up",
    "सोयाबीन": "soybean soyabean BBF weed",
    "खाद": "fertilizer urea DAP NPK manure",
    "सिंचाई": "irrigation watering CRI stage",
    "उर्वरक": "chemical fertilizer NPK",
    "कीटनाशक": "insecticide pesticide spray",
    "फफूंदनाशक": "fungicide spray",
    "पीएम किसान": "PM-KISAN Samman Nidhi 6000 installment eKYC land seeding",
    "फसल बीमा": "PM Fasal Bima PMFBY crop insurance claim 72 hours",
    "किसान क्रेडिट": "Kisan Credit Card KCC loan 4 percent",
    "मृदा स्वास्थ्य": "Soil Health Card testing 12 parameters",
    "कुसुम": "PM-KUSUM solar agricultural pump subsidy",
    "ड्रिप": "drip micro irrigation subsidy maintenance acid treatment",
    "इलाज": "treatment control management spray remedy",
    "रोकथाम": "prevention control treatment management",
    "उपचार": "treatment control remedy spray"
}

class LocalSentenceTransformerEmbedding(EmbeddingFunction):
    """
    High-performance, local embedding function using SentenceTransformer
    (defaults to cached 'sentence-transformers/all-MiniLM-L6-v2').
    Runs completely offline with 0 network latency and bilingual query expansion.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", local_files_only: bool = True):
        self.model_name = os.environ.get("EMBEDDING_MODEL_PATH") or os.environ.get("EMBEDDING_MODEL_NAME") or model_name
        self.local_files_only = local_files_only
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            model_target = os.environ.get("EMBEDDING_MODEL_PATH") or self.model_name
            offline_forced = os.environ.get("EMBEDDING_LOCAL_FILES_ONLY", "").lower() in ("1", "true", "yes")

            # 1. Attempt local load first
            try:
                self._model = SentenceTransformer(model_target, local_files_only=True)
                return self._model
            except Exception as local_err:
                if offline_forced:
                    raise RuntimeError(
                        f"Failed to load embedding model '{model_target}' from local cache: {local_err}. "
                        "EMBEDDING_LOCAL_FILES_ONLY is enabled. Please pre-cache the model or configure EMBEDDING_MODEL_PATH."
                    ) from local_err

                # 2. Attempt online download if offline is not strictly forced
                try:
                    self._model = SentenceTransformer(model_target, local_files_only=False)
                    return self._model
                except Exception as dl_err:
                    raise RuntimeError(
                        f"Failed to load embedding model '{model_target}'. "
                        f"Local cache check failed ({local_err}) and online download failed: {dl_err}. "
                        "Please verify your internet connection or configure EMBEDDING_MODEL_PATH to a pre-cached model folder."
                    ) from dl_err
        return self._model

    def __call__(self, input: Documents) -> Embeddings:
        """Embeds a list of text documents or queries into normalized dense vectors."""
        if not input:
            return []

        cleaned_inputs = [str(text).strip() if text else " " for text in input]
        model = self._get_model()

        raw_embeddings = model.encode(
            cleaned_inputs,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True
        )

        return raw_embeddings.tolist()

    def embed_query(self, input: Union[List[str], str], **kwargs) -> Embeddings:
        """Embeds query inputs (list of strings or single string), applying bilingual query expansion."""
        if isinstance(input, str):
            input_list = [input]
        else:
            input_list = list(input)

        expanded = [self.expand_query(q) for q in input_list]
        return self.__call__(expanded)

    @staticmethod
    def expand_query(query: str) -> str:
        """
        Enhances Hindi Devanagari and Hinglish queries by appending canonical domain synonyms
        so English-centric embedding models (MiniLM) can match the English domain documentation.
        """
        lower_q = query.lower()
        expansions = []

        # Sort keys by length descending to match phrases like "gulabi sundi" before "sundi"
        sorted_keys = sorted(AGRI_SYNONYMS.keys(), key=len, reverse=True)

        for key in sorted_keys:
            syn = AGRI_SYNONYMS[key]
            if key in lower_q or key in query:
                # Add if not already largely covered
                if not any(token in lower_q for token in syn.split()[:2]):
                    expansions.append(syn)
            if len(expansions) >= 3:
                break

        if expansions:
            return f"{query} [Agri Domain: {' | '.join(expansions)}]"
        return query


def get_embedding_function(model_name: str = "sentence-transformers/all-MiniLM-L6-v2", local_files_only: bool = True):
    return LocalSentenceTransformerEmbedding(model_name=model_name, local_files_only=local_files_only)
