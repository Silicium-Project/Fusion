/** Idempotent Project schema setup. Existing option IDs and metadata are preserved. */
import { graphql } from '../lib/github.mjs';
import { projectState, fieldValues, setField } from '../lib/project.mjs';
const apply = process.argv.includes('--apply');
let project = projectState();
const definitions = [
  {
    name: 'Préparation',
    dataType: 'SINGLE_SELECT',
    singleSelectOptions: [
      { name: 'À compléter', color: 'GRAY', description: 'Critères de démarrage incomplets' },
      {
        name: 'Validée',
        color: 'GREEN',
        description: 'Préparation et cible explicitement acceptées',
      },
    ],
  },
  {
    name: 'Validation cible',
    dataType: 'SINGLE_SELECT',
    singleSelectOptions: ['Documentation', 'CI', 'Dev', 'Prod'].map((name) => ({
      name,
      color: 'BLUE',
      description: `Preuves requises : ${name}`,
    })),
  },
  { name: 'Blocage', dataType: 'TEXT' },
];
const operations = [];
for (const definition of definitions)
  if (!project.fields.nodes.some((f) => f.name === definition.name)) {
    operations.push({ operation: 'create-field', ...definition });
    if (apply)
      graphql(
        'mutation($input:CreateProjectV2FieldInput!){createProjectV2Field(input:$input){projectV2Field{... on ProjectV2Field{id} ... on ProjectV2SingleSelectField{id}}}}',
        { input: { projectId: project.id, ...definition } },
      );
  }
const status = project.fields.nodes.find((f) => f.name === 'Status');
if (!status.options.some((o) => o.name === 'Abandonné')) {
  const f = graphql(
    'query($id:ID!){node(id:$id){... on ProjectV2SingleSelectField{options{id name color description}}}}',
    { id: status.id },
  ).node;
  operations.push({ operation: 'add-option', field: 'Status', name: 'Abandonné' });
  if (apply)
    graphql(
      'mutation($input:UpdateProjectV2FieldInput!){updateProjectV2Field(input:$input){projectV2Field{... on ProjectV2SingleSelectField{id}}}}',
      {
        input: {
          fieldId: status.id,
          singleSelectOptions: [
            ...f.options,
            {
              name: 'Abandonné',
              color: 'GRAY',
              description: 'Abandon ou doublon décidé explicitement, sans comptage comme livré',
            },
          ],
        },
      },
    );
}
if (apply) {
  project = projectState();
  for (const item of project.items) {
    const f = fieldValues(item);
    if (f.Status === 'Prêt' && item.content?.assignees.nodes.length && f.Size) {
      setField(project, item.id, 'Préparation', 'Validée');
      setField(
        project,
        item.id,
        'Validation cible',
        item.content.body.includes('EXEC-02') ? 'CI' : 'Documentation',
      );
    }
  }
}
console.log(JSON.stringify({ schema_version: 1, apply, operations }, null, 2));
