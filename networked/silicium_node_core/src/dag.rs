use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use thiserror::Error;

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

    pub fn validate(&self) -> Result<(), DagError> {
        for (id, node) in &self.nodes {
            if id.trim().is_empty() {
                return Err(DagError::EmptyNodeId);
            }

            let mut parents = BTreeSet::new();
            for parent in &node.parents {
                if parent == id {
                    return Err(DagError::SelfDependency { node: id.clone() });
                }
                if !self.nodes.contains_key(parent) {
                    return Err(DagError::UnknownParent {
                        node: id.clone(),
                        parent: parent.clone(),
                    });
                }
                if !parents.insert(parent) {
                    return Err(DagError::DuplicateParent {
                        node: id.clone(),
                        parent: parent.clone(),
                    });
                }
            }
        }

        let mut indegree: BTreeMap<String, usize> = self
            .nodes
            .keys()
            .map(|id| (id.clone(), 0))
            .collect();
        for node in self.nodes.values() {
            for parent in &node.parents {
                *indegree
                    .get_mut(&node.id)
                    .expect("node IDs are present in the graph") += 1;
                debug_assert!(self.nodes.contains_key(parent));
            }
        }

        let mut ready: VecDeque<String> = indegree
            .iter()
            .filter(|(_, degree)| **degree == 0)
            .map(|(id, _)| id.clone())
            .collect();
        let mut visited = 0;
        while let Some(id) = ready.pop_front() {
            visited += 1;
            for node in self.nodes.values() {
                if node.parents.iter().any(|parent| parent == &id) {
                    let degree = indegree
                        .get_mut(&node.id)
                        .expect("node IDs are present in the graph");
                    *degree -= 1;
                    if *degree == 0 {
                        ready.push_back(node.id.clone());
                    }
                }
            }
        }

        if visited != self.nodes.len() {
            return Err(DagError::Cycle);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum DagError {
    #[error("DAG node ID cannot be empty")]
    EmptyNodeId,
    #[error("DAG node '{node}' references unknown parent '{parent}'")]
    UnknownParent { node: String, parent: String },
    #[error("DAG node '{node}' references parent '{parent}' more than once")]
    DuplicateParent { node: String, parent: String },
    #[error("DAG node '{node}' cannot depend on itself")]
    SelfDependency { node: String },
    #[error("DAG contains a cycle")]
    Cycle,
    #[error("DAG node '{0}' does not exist")]
    UnknownNode(String),
    #[error("DAG node '{0}' is not currently dispatched")]
    NotInFlight(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DagScheduler {
    ready: VecDeque<String>,
    completed: BTreeSet<String>,
    in_flight: BTreeSet<String>,
    graph: DagGraph,
}

impl DagScheduler {
    pub fn new(graph: DagGraph) -> Self {
        Self::try_new(graph).expect("DAG scheduler requires a valid acyclic graph")
    }

    pub fn try_new(graph: DagGraph) -> Result<Self, DagError> {
        graph.validate()?;
        let ready = graph
            .nodes
            .values()
            .filter(|node| node.parents.is_empty())
            .map(|node| node.id.clone())
            .collect();
        Ok(Self {
            ready,
            completed: BTreeSet::new(),
            in_flight: BTreeSet::new(),
            graph,
        })
    }

    pub fn ready(&self) -> impl Iterator<Item = &String> {
        self.ready.iter()
    }

    pub fn pop_ready(&mut self) -> Option<String> {
        let node_id = self.ready.pop_front()?;
        self.in_flight.insert(node_id.clone());
        Some(node_id)
    }

    pub fn mark_complete(&mut self, node_id: impl Into<String>) -> Result<(), DagError> {
        let node_id = node_id.into();
        if !self.graph.nodes.contains_key(&node_id) {
            return Err(DagError::UnknownNode(node_id));
        }
        if !self.in_flight.remove(&node_id) {
            return Err(DagError::NotInFlight(node_id));
        }
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
        Ok(())
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
        scheduler.mark_complete("geometry").unwrap();
        assert!(scheduler.is_ready("compositing"));
    }

    #[test]
    fn completion_before_dispatch_is_rejected() {
        let graph = DagGraph::from_nodes([DagNode {
            id: "geometry".into(),
            parents: vec![],
            children: vec![],
            runtime: None,
        }]);
        let mut scheduler = DagScheduler::new(graph);

        assert_eq!(
            scheduler.mark_complete("geometry"),
            Err(DagError::NotInFlight("geometry".into()))
        );
        assert!(scheduler.is_ready("geometry"));
    }

    #[test]
    fn invalid_graphs_are_rejected_before_dispatch() {
        let graph = DagGraph::from_nodes([
            DagNode {
                id: "geometry".into(),
                parents: vec!["compositing".into()],
                children: vec![],
                runtime: None,
            },
            DagNode {
                id: "compositing".into(),
                parents: vec!["geometry".into()],
                children: vec![],
                runtime: None,
            },
        ]);

        assert_eq!(DagScheduler::try_new(graph), Err(DagError::Cycle));
    }
}
