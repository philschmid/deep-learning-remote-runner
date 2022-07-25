import argparse
import logging
import sys
import time
import numpy as np
from datasets import load_dataset, load_metric
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from transformers import AutoTokenizer
from optimum.habana import GaudiTrainer, GaudiTrainingArguments

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # hyperparameters sent by the client are passed as command-line arguments to the script.
    parser.add_argument("--model_id", type=str)
    parser.add_argument("--dataset_id", type=str)
    parser.add_argument("--save_repository_id", type=str)
    parser.add_argument("--hf_hub_token", type=str)
    parser.add_argument("--num_train_epochs", type=int)
    parser.add_argument("--per_device_train_batch_size", type=int, default=32)
    parser.add_argument("--per_device_eval_batch_size", type=int, default=32)
    args, _ = parser.parse_known_args()

    gaudi_config_id = "Habana/distilbert-base-uncased"  # more here: https://huggingface.co/Habana

    # Set up logging
    logger = logging.getLogger(__name__)

    logging.basicConfig(
        level=logging.getLevelName("INFO"),
        handlers=[logging.StreamHandler(sys.stdout)],
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)

    # load datasets
    dataset = load_dataset(args.dataset_id)

    # process dataset
    def process(examples):
        tokenized_inputs = tokenizer(examples["text"], padding=True, truncation=True, max_length=512)
        return tokenized_inputs

    tokenized_datasets = dataset.map(process, batched=True)
    tokenized_datasets = tokenized_datasets.rename_column("label", "labels")

    metric = load_metric("accuracy")

    def compute_metrics(eval_pred):
        predictions, labels = eval_pred
        predictions = np.argmax(predictions, axis=1)
        return metric.compute(predictions=predictions, references=labels)

    # create label2id, id2label dicts for nice outputs for the model
    labels = tokenized_datasets["train"].features["labels"].names
    num_labels = len(labels)
    label2id, id2label = dict(), dict()
    for i, label in enumerate(labels):
        label2id[label] = str(i)
        id2label[str(i)] = label

    # download model from model hub
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_id, num_labels=num_labels, label2id=label2id, id2label=id2label
    )

    training_args = GaudiTrainingArguments(
        output_dir=args.save_repository_id,
        use_habana=True,
        use_lazy_mode=True,
        gaudi_config_name=gaudi_config_id,
        num_train_epochs=args.num_train_epochs,
        per_device_train_batch_size=args.per_device_train_batch_size,
        per_device_eval_batch_size=args.per_device_eval_batch_size,
        learning_rate=3e-5,
        # logging & evaluation strategies
        logging_dir=f"{args.save_repository_id}/logs",
        logging_strategy="epoch",
        evaluation_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        report_to="tensorboard",
        # push to hub parameters
        push_to_hub=True,
        hub_strategy="every_save",
        hub_model_id=args.save_repository_id,
        hub_token=args.hf_hub_token,
    )
    # create Trainer
    trainer = GaudiTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets["test"].shuffle().select(range(5000)),  # smaller eval size
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )

    # start training
    trainer.train()
    # evaluate model
    trainer.evaluate(eval_dataset=tokenized_datasets["test"])
    # create model card
    time.sleep(15)
    trainer.create_model_card()
