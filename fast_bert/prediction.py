import torch
from pathlib import Path

from .onnx_helper import load_model

from .learner_ner import group_entities
from .data_ner import get_labels

from transformers import AutoTokenizer
import numpy as np

import warnings

warnings.filterwarnings("ignore", message="numpy.dtype size changed")
warnings.filterwarnings("ignore", message="numpy.ufunc size changed")


class BertClassificationPredictor(object):
    def __init__(
        self,
        model_path,
        label_path,
        multi_label=False,
        model_type="bert",
        use_fast_tokenizer=True,
        do_lower_case=True,
        device=None,
    ):
        if device is None:
            device = (
                torch.device("cuda")
                if torch.cuda.is_available()
                else torch.device("cpu")
            )

        self.model_path = model_path
        self.label_path = label_path
        self.multi_label = multi_label
        self.model_type = model_type
        self.do_lower_case = do_lower_case
        self.device = device

        # Use auto-tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, use_fast=use_fast_tokenizer
        )

        self.learner = self.get_learner()

    def get_learner(self):
        from .learner_cls import BertLearner
        from .data_cls import BertDataBunch

        databunch = BertDataBunch(
            self.label_path,
            self.label_path,
            self.tokenizer,
            train_file=None,
            val_file=None,
            batch_size_per_gpu=32,
            max_seq_length=512,
            multi_gpu=False,
            multi_label=self.multi_label,
            model_type=self.model_type,
            no_cache=True,
        )

        learner = BertLearner.from_pretrained_model(
            databunch,
            self.model_path,
            metrics=[],
            device=self.device,
            logger=None,
            output_dir=None,
            warmup_steps=0,
            multi_gpu=False,
            is_fp16=False,
            multi_label=self.multi_label,
            logging_steps=0,
        )

        return learner

    def predict_batch(self, texts, verbose=False):
        return self.learner.predict_batch(texts, verbose=verbose)

    def predict(self, text, verbose=False):
        predictions = self.predict_batch([text], verbose=verbose)[0]
        return predictions


class BertOnnxClassificationPredictor(object):
    def __init__(
        self,
        model_path,
        label_path,
        model_name="model.onnx",
        multi_label=False,
        model_type="bert",
        use_fast_tokenizer=True,
        do_lower_case=True,
        device=None,
    ):
        if device is None:
            device = (
                torch.device("cuda")
                if torch.cuda.is_available()
                else torch.device("cpu")
            )

        self.model_path = model_path
        self.label_path = label_path
        self.multi_label = multi_label
        self.model_type = model_type
        self.do_lower_case = do_lower_case
        self.device = device
        self.labels = []

        # Use auto-tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, use_fast=use_fast_tokenizer
        )

        with open(label_path / "labels.csv", "r") as f:
            self.labels = f.read().split("\n")

        self.model = load_model(Path(self.model_path) / model_name)

    def predict(self, text, verbose=False):
        # Inputs are provided through numpy array
        model_inputs = self.tokenizer(text, return_tensors="pt")
        inputs_onnx = {k: v.cpu().detach().numpy() for k, v in model_inputs.items()}
        outputs = self.model.run(None, inputs_onnx)
        softmax_preds = softmax(outputs[0])
        preds = list(zip(self.labels, softmax_preds[0]))
        return sorted(preds, key=lambda x: x[1], reverse=True)


class BertNERPredictor(object):
    def __init__(
        self,
        model_path,
        label_path,
        model_type="bert",
        use_fast_tokenizer=True,
        do_lower_case=True,
        device=None,
    ):
        if device is None:
            device = (
                torch.device("cuda")
                if torch.cuda.is_available()
                else torch.device("cpu")
            )

        self.model_path = model_path
        self.label_path = label_path
        self.model_type = model_type
        self.do_lower_case = do_lower_case
        self.device = device

        # Use auto-tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, use_fast=use_fast_tokenizer
        )

        self.learner = self.get_learner()

    def get_learner(self):
        from .data_ner import BertNERDataBunch
        from .learner_ner import BertNERLearner

        databunch = BertNERDataBunch(
            self.label_path,
            self.tokenizer,
            train_file=None,
            val_file=None,
            batch_size_per_gpu=32,
            max_seq_length=512,
            multi_gpu=False,
            model_type=self.model_type,
            no_cache=True,
        )

        learner = BertNERLearner.from_pretrained_model(
            databunch,
            self.model_path,
            device=self.device,
            logger=None,
            output_dir=None,
            warmup_steps=0,
            multi_gpu=False,
            is_fp16=False,
            logging_steps=0,
        )

        return learner

    def predict_batch(self, texts, group=True, exclude_entities=["O"]):
        predictions = []

        for text in texts:
            pred = self.predict(text, group=group, exclude_entities=exclude_entities)
            if pred:
                predictions.append({"text": text, "results": pred})

    def predict(self, text, group=True, exclude_entities=["O"]):
        predictions = self.learner.predict(
            text, group=group, exclude_entities=exclude_entities
        )
        return predictions


class BertOnnxNERPredictor(object):
    def __init__(
        self,
        model_path,
        label_path,
        model_name="model.onnx",
        model_type="bert",
        use_fast_tokenizer=True,
        do_lower_case=True,
        device=None,
    ):
        if device is None:
            device = (
                torch.device("cuda")
                if torch.cuda.is_available()
                else torch.device("cpu")
            )

        self.model_path = model_path
        self.label_path = label_path
        self.model_type = model_type
        self.do_lower_case = do_lower_case
        self.device = device
        self.labels = []

        # Use auto-tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, use_fast=use_fast_tokenizer
        )

        self.labels = get_labels(str(label_path / "labels.txt"))

        self.model = load_model(Path(self.model_path) / model_name)

    def predict(self, text, group=True, exclude_entities=["O"]):
        # Inputs are provided through numpy array
        tokens = self.tokenizer.tokenize(
            self.tokenizer.decode(self.tokenizer.encode(text))
        )

        model_inputs = self.tokenizer(text, return_tensors="pt")
        inputs_onnx = {k: v.cpu().detach().numpy() for k, v in model_inputs.items()}
        outputs = self.model.run(None, inputs_onnx)[0]
        outputs = softmax(outputs)

        predictions = np.argmax(outputs, axis=2)

        preds = [
            (token, self.labels[prediction], output[prediction])
            for token, output, prediction in zip(tokens, outputs[0], predictions[0])
        ][1:-1]

        preds = [
            {
                "index": index,
                "word": prediction[0],
                "entity": prediction[1],
                "score": prediction[2],
            }
            for index, prediction in enumerate(preds)
        ]

        if group is True:
            preds = group_entities(preds)

        out_preds = []
        for pred in preds:
            if pred["entity"] not in exclude_entities:
                try:
                    pred["entity"] = pred["entity"].split("-")[1]
                except Exception:
                    pass

                out_preds.append(pred)

        return out_preds

    def predict_batch(self, texts, group=True, exclude_entities=["O"]):
        predictions = []

        for text in texts:
            pred = self.predict(text, group=group, exclude_entities=exclude_entities)
            if pred:
                predictions.append({"text": text, "results": pred})


def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    x_max = np.max(x, axis=axis, keepdims=True)
    tmp = np.exp(x - x_max)
    s = np.sum(tmp, axis=axis, keepdims=True)
    return tmp / s
