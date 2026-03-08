# **Protocole de communication Silicium Chain**

Version 1.0

# **Objectif**

Ce protocole sert à relier :

- le moteur off-chain de calcul et de vérification  

- le layer on-chain **Silicium Chain  

Le protocole ne fait **pas le calcul**.

Le protocole ne remplace **pas le smart contract**.

Il décrit uniquement comment représenter, en **JSON**, les actions à transformer en appels vers les instructions du layer.

Chaque message doit être interprété comme :

voici l'intention métier à exécuter on-chain

# **Enveloppe commune de tous les messages**

Tous les messages doivent respecter ce format général :
```json
{
    "version": "1.0",
    "message_type": "string",
    "request_id": "uuid-or-unique-id",
    "timestamp_unix": 1760000000,
    "source": {
    "role": "client|scheduler|worker|verifier|slasher|system",
    "id": "logical-identifier"
    },
    "payload": {}
}
```

## **Signification des champs**

### **version**
- version du protocole  

### **message_type**
- type métier du message  

### **request_id**
- identifiant unique du message  
- utilisé pour corréler les réponses  

### **timestamp_unix**
- timestamp d'émission du message  

### **source**
- Contient l'origine logique du message.

#### **role**
Peut être :
- client  
- worker  
- verifier  
- system  

#### **id**
Identifiant logique du composant qui émet le message.

### **payload**
Contient les données utiles pour appeler l'instruction on-chain.

# **Identifiants et conventions**
## **Identifiants utilisés dans le protocole**
Les champs suivants sont utilisés dans plusieurs messages :
- job_id  
- job_pda 
- fragment_index  
- round  
- worker_pubkey  
- verifier_pubkey  
- mint  
- result_hash  
- proof_ref  
- worker_token_account  

## **Identification d'un fragment**

Un fragment est identifié par :
- job_id  
- fragment_index  
- round  

## **Identification d'un vote**

Un vote est identifié par :
- job_id  
- fragment_index  
- round  
- verifier_pubkey  

# **Correspondance message → instruction**

| **Message** | **Instruction** |
| --- | --- |
| create_job_request | create_job |
| --- | --- |
| register_worker_request | register_worker |
| --- | --- |
| stake_worker_request | stake_worker |
| --- | --- |
| submit_fragment_result_request | submit_fragment_result |
| --- | --- |
| vote_fragment_request | vote_fragment |
| --- | --- |
| resubmit_fragment_result_request | resubmit_fragment_result |
| --- | --- |
| init_treasury_request | init_treasury |
| --- | --- |
| slash_vote_request | slash_vote |
| --- | --- |
| finalize_job_request | finalize_job |
| --- | --- |
| cancel_job_request | cancel_job |
| --- | --- |

# **Messages du protocole**

# **create_job_request**

## **But**

Créer un job on-chain et déposer les fonds dans l'escrow.

### **Instruction appelée**

create_job

### **JSON**

```JSON
{
    "version": "1.0",
    "message_type": "create_job_request",
    "request_id": "req-create-job-0001",
    "timestamp_unix": 1760000000,
    "source": {
        "role": "client",
        "id": "client-ui"
    },
    "payload": {
    "job_id": 42,
    "client_pubkey": "CLIENT_PUBKEY",
    "mint": "MINT_PUBKEY",
    "expected_fragments": 8,
    "reward_per_fragment": 1000000,
    "deadline_unix": 1760003600,
    "fragment_quorum": 2
    }
}
```

### **Champs obligatoires**

- job_id  

- client_pubkey  

- mint  

- expected_fragments  

- reward_per_fragment  

- deadline_unix  

- fragment_quorum  

### **Résultat on-chain**

- création du compte Job  

- création de l'escrow  

- dépôt des fonds  

# **register_worker_request**

## **But**

Créer un worker dans le layer.

### **Instruction appelée**

register_worker

### **JSON**

```JSOn
{
"version": "1.0",
"message_type": "register_worker_request",
"request_id": "req-register-worker-0001",
"timestamp_unix": 1760000010,
"source": {
"role": "worker",
"id": "worker-node-1"
},
"payload": {
"worker_pubkey": "WORKER_PUBKEY"
}
}
```

### **Résultat on-chain**

- création du compte Worker  

- statut Active  

# **stake_worker_request**

## **But**

Permet à un worker de déposer du stake.

### **Instruction appelée**

stake_worker

### **JSON**

```json
{

"version": "1.0",

"message_type": "stake_worker_request",

"request_id": "req-stake-worker-0001",

"timestamp_unix": 1760000020,

"source": {

"role": "worker",
"id": "worker-node-1"
},
"payload": {
"worker_pubkey": "WORKER_PUBKEY",
"mint": "MINT_PUBKEY",
"worker_token_account": "WORKER_TOKEN_ACCOUNT",
"amount": 1000000
}
}
```

### **Effets on-chain**

- création du stake vault  

- transfert des tokens  

- mise à jour du stake  

# **submit_fragment_result_request**

## **But**

Soumettre un fragment calculé off-chain.

### **Instruction appelée**

submit_fragment_result

### **JSON**

```JSON
{
"version": "1.0",
"message_type": "submit_fragment_result_request",
"request_id": "req-submit-fragment-0001",
"timestamp_unix": 1760000100,
"source": {
"role": "worker",
"id": "worker-node-7"
},
"payload": {
"job_id": 42,
"job_pda": "JOB_PDA",
"fragment_index": 3,
"worker_pubkey": "WORKER_PUBKEY",
"worker_token_account": "WORKER_TOKEN_ACCOUNT",
"result_hash": \[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1\],
"proof_ref": \[2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2\]
}
}

### **Effets on-chain**

- création du fragment  

- status = Submitted  

- stockage du résultat  

- stockage du worker  

# **vote_fragment_request**

## **But**

Permet à un verifier de voter pour un fragment.

### **Instruction appelée**

vote_fragment

### **JSON**
{
"version": "1.0",
"message_type": "vote_fragment_request",
"request_id": "req-vote-fragment-0001",
"timestamp_unix": 1760000200,
"source": {
"role": "verifier",
"id": "verifier-node-2"
},
"payload": {
"job_id": 42,
"job_pda": "JOB_PDA",
"fragment_index": 3,
"fragment_pda": "FRAGMENT_PDA",
"round": 0,
"verifier_pubkey": "VERIFIER_PUBKEY",
"choice": true
}
}
```

### **Effets on-chain**

- création du FragmentVote  

- incrément du compteur YES ou NO  

Si quorum atteint :

- Verified  

- paiement du worker  

# **resubmit_fragment_result_request**

## **But**

Relancer un fragment rejeté avec un nouveau round.

### **Instruction appelée**

resubmit_fragment_result

### **JSON**

```JSoN
{
"version": "1.0",
"message_type": "resubmit_fragment_result_request",
"request_id": "req-resubmit-fragment-0001",
"timestamp_unix": 1760000300,
"source": {
"role": "worker",
"id": "worker-node-9"
},
"payload": {
"job_id": 42,
"job_pda": "JOB_PDA",
"fragment_index": 3,
"previous_round": 0,
"new_round": 1,
"worker_pubkey": "NEW_WORKER_PUBKEY",
"worker_token_account": "NEW_WORKER_TOKEN_ACCOUNT",
"result_hash": \[9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9\],
"proof_ref": \[8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8\]
}
}
```

### **Effets on-chain**
- round += 1  
- reset votes  
- nouveau worker  
- status = Submitted  

# **slash_vote_request**

## **But**

Punir un vote incorrect.

### **Instruction appelée**

slash_vote

### **JSON**

```JSON
{
"version": "1.0",
"message_type": "slash_vote_request",
"request_id": "req-slash-vote-0001",
"timestamp_unix": 1760000500,
"source": {
"role": "slasher",
"id": "slasher-bot"
},
"payload": {
"job_id": 42,
"fragment_index": 3,
"round": 0,
"verifier_pubkey": "BAD_VERIFIER"
}
}
```

### **Effets on-chain**

- transfert du stake vers le treasury  

- marquage du vote comme slashed  

# **finalize_job_request**

## **But**

Finaliser un job.

### **Instruction appelée**

finalize_job

### **JSON**

```Json
{
"version": "1.0",
"message_type": "finalize_job_request",
"request_id": "req-finalize-job-0001",
"timestamp_unix": 1760000600,
"source": {
"role": "client",
"id": "client-ui"
},
"payload": {
"job_id": 42,
"job_pda": "JOB_PDA",
"client_pubkey": "CLIENT_PUBKEY",
"final_hash": \[7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7\],
"output_uri": "ipfs://result"
}
}
```

### **Effets on-chain**

- création JobResult  

- remboursement du reste  

- fermeture escrow  

- status = Finalized  

# **cancel_job_request**

## **But**

Annuler un job.

### **Instruction appelée**

cancel_job

### **JSON**

```Json
{
"version": "1.0",
"message_type": "cancel_job_request",
"request_id": "req-cancel-job-0001",
"timestamp_unix": 1760000700,
"source": {
"role": "client",
"id": "client-ui"
},
"payload": {
"job_id": 42,
"job_pda": "JOB_PDA",
"client_pubkey": "CLIENT_PUBKEY"
}
}
```

### **Effets on-chain**

- remboursement  

- fermeture escrow  

- status = Cancelled  
