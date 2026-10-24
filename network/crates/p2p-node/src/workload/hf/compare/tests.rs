//! Metrics of the verifiers, on outputs shaped as the runtime writes them.

use super::*;
use serde_json::json;

#[test]
fn labels_compare_the_top_one() {
    let a = json!([{"label": "cat", "score": 0.9}, {"label": "dog", "score": 0.1}]);
    let b = json!([{"label": "dog", "score": 0.2}, {"label": "cat", "score": 0.8}]);
    assert_eq!(Metric::Label.similarity(&a, &b), 1.0);
    let c = json!([{"label": "dog", "score": 0.6}, {"label": "cat", "score": 0.4}]);
    assert_eq!(Metric::Label.similarity(&a, &c), 0.0);
    let zero_shot = json!({"sequence": "x", "labels": ["sport", "art"], "scores": [0.7, 0.3]});
    assert_eq!(Metric::Label.similarity(&zero_shot, &zero_shot), 1.0);
    let mask = json!([{"token_str": "Paris", "score": 0.9}]);
    assert_eq!(Metric::Label.similarity(&mask, &mask), 1.0);
}

#[test]
fn texts_vectors_and_scores_tolerate_rounding() {
    let a = json!([{"generated_text": "Le chat dort sur le canapé."}]);
    let b = json!([{"generated_text": "Le chat dort sur le canapé rouge."}]);
    assert!(Metric::Text.similarity(&a, &b) > 0.8);
    assert!(
        Metric::Vector.similarity(&json!([0.1, 0.2, 0.3]), &json!([0.1001, 0.2, 0.2999])) > 0.999
    );
    assert_eq!(
        Metric::Vector.similarity(&json!([1, 0]), &json!([1, 0, 0])),
        0.0
    );
    assert_eq!(
        Metric::Scores.similarity(&json!([0.5, 0.7]), &json!([0.505, 0.695])),
        1.0
    );
    assert_eq!(Metric::Scores.similarity(&json!([0.5]), &json!([0.6])), 0.0);
}

#[test]
fn speech_ranking_entities_answers_and_boxes() {
    let wer = Metric::Wer.similarity(
        &json!({"text": "bonjour à tous"}),
        &json!({"text": "bonjour a tous"}),
    );
    assert!((wer - 2.0 / 3.0).abs() < 1e-9);
    let rank_a =
        json!([{"index": 0, "score": 0.9}, {"index": 2, "score": 0.5}, {"index": 1, "score": 0.1}]);
    let rank_b =
        json!([{"index": 2, "score": 0.8}, {"index": 0, "score": 0.7}, {"index": 1, "score": 0.1}]);
    assert!((Metric::Ranking.similarity(&rank_a, &rank_b) - 2.0 / 3.0).abs() < 1e-9);
    let ents =
        json!([{"entity_group": "PER", "word": "Marie"}, {"entity_group": "LOC", "word": "Lyon"}]);
    let ents2 = json!([{"entity_group": "PER", "word": "marie"}]);
    assert!((Metric::Entities.similarity(&ents, &ents2) - 2.0 / 3.0).abs() < 1e-9);
    assert_eq!(
        Metric::AnswerF1.similarity(&json!({"answer": "en 1905"}), &json!({"answer": "En 1905"})),
        1.0
    );
    let det_a = json!([{"label": "cat", "score": 0.9, "box": {"xmin": 0, "ymin": 0, "xmax": 10, "ymax": 10}}]);
    let det_b = json!([{"label": "cat", "score": 0.8, "box": {"xmin": 1, "ymin": 1, "xmax": 10, "ymax": 10}}]);
    assert_eq!(Metric::Boxes.similarity(&det_a, &det_b), 1.0);
    let det_c = json!([{"label": "dog", "score": 0.8, "box": {"xmin": 0, "ymin": 0, "xmax": 10, "ymax": 10}}]);
    assert_eq!(Metric::Boxes.similarity(&det_a, &det_c), 0.0);
}

#[test]
fn thresholds_need_the_mean_and_every_item() {
    assert!(Metric::Text.accept(&[0.9, 0.7, 0.5]));
    assert!(!Metric::Text.accept(&[1.0, 1.0, 0.1]));
    assert!(Metric::Label.accept(&[1.0, 1.0, 0.0]));
    assert!(!Metric::Label.accept(&[1.0, 0.0, 0.0]));
    assert!(!Metric::Label.accept(&[]));
}

#[test]
fn every_task_is_a_task_of_the_hub_page() {
    assert_eq!(TASKS.len(), 19);
    assert_eq!(metric("object-detection"), Some(Metric::Boxes));
    assert_eq!(metric("text-to-video"), None);
}
