from enum import StrEnum


class CommandName(StrEnum):
    preprocess_data = "preprocess_data"
    pretrain = "pretrain"
    train_supervised = "train_supervised"
    predict_supervised = "predict_supervised"
    train_finetune = "train_finetune"
    predict_finetune = "predict_finetune"
    infer_embeddings = "infer_embeddings"
    train_probe = "train_probe"
    predict_probe = "predict_probe"
    predict_zero_shot_direct = "predict_zero_shot_direct"
    infer_trajectories = "infer_trajectories"
    predict_zero_shot_materialized = "predict_zero_shot_materialized"
    predict_only = "predict_only"


class ArtifactType(StrEnum):
    patients = "patients"
    pretrained_model = "pretrained_model"
    embeddings = "embeddings"
    trajectories = "trajectories"
    supervised_model = "supervised_model"
    finetuned_model = "finetuned_model"
    probe_model = "probe_model"
    predictions = "predictions"
