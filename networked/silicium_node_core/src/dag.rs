use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DagNode {
    pub id: String,
    #[serde(default)]
    pub parents: Vec<String>,
    #[serde(default)]
    pub children: Vec<String>,
    #[serde(default)]
    pub runtime: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct DagGraph {
    pub nodes: BTreeMap<String, DagNode>,
}

impl DagGraph {
    pub fn insert(&mut self, node: DagNode) {
        self.nodes.insert(node.id.clone(), node);
    }

    pub fn from_nodes(nodes: impl IntoIterator<Item = DagNode>) -> Self {
        let mut graph = Self::default();
        for node in nodes {
            graph.insert(node);
        }
        graph
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DagScheduler {
    ready: VecDeque<String>,
    completed: BTreeSet<String>,
    graph: DagGraph,
}

impl DagScheduler {
    pub fn new(graph: DagGraph) -> Self {
        let ready = graph
            .nodes
            .values()
            .filter(|node| node.parents.is_empty())
            .map(|node| node.id.clone())
            .collect();
        Self {
            ready,
            completed: BTreeSet::new(),
            graph,
        }
    }

    pub fn ready(&self) -> impl Iterator<Item = &String> {
        self.ready.iter()
    }

    pub fn pop_ready(&mut self) -> Option<String> {
        self.ready.pop_front()
    }

    pub fn mark_complete(&mut self, node_id: impl Into<String>) {
        let node_id = node_id.into();
        self.completed.insert(node_id.clone());

        for node in self.graph.nodes.values() {
            if self.completed.contains(&node.id) || self.ready.contains(&node.id) {
                continue;
            }

            if node
                .parents
                .iter()
                .all(|parent| self.completed.contains(parent))
            {
                self.ready.push_back(node.id.clone());
            }
        }
    }

    pub fn is_ready(&self, node_id: &str) -> bool {
        self.ready.iter().any(|candidate| candidate == node_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parent_tasks_gate_children() {
        let graph = DagGraph::from_nodes([
            DagNode {
                id: "geometry".into(),
                parents: vec![],
                children: vec!["compositing".into()],
                runtime: Some("wasm".into()),
            },
            DagNode {
                id: "compositing".into(),
                parents: vec!["geometry".into()],
                children: vec![],
                runtime: Some("oci".into()),
            },
        ]);
        let mut scheduler = DagScheduler::new(graph);
        assert_eq!(scheduler.pop_ready().as_deref(), Some("geometry"));
        assert!(scheduler.pop_ready().is_none());
        scheduler.mark_complete("geometry");
        assert!(scheduler.is_ready("compositing"));
    }
}
