# FrontEnd

## Build
Launch using docker compose

```shell
docker compose up --build 
```
Ports :  
Frontend -> 3000

## Silicium bridge configuration

The dashboard submits jobs to the backend and opens the read-only Devnet
dashboard through public runtime config:

```shell
NUXT_PUBLIC_API_BASE=http://localhost:8080
NUXT_PUBLIC_DEVNET_DASHBOARD_URL=http://localhost:5174/
```

## Current Mock-up for the website (10/30)
<img width="1440" height="1024" alt="Silicium - Landing Page" src="https://github.com/user-attachments/assets/f66531ff-c48a-4c11-895f-51093b0a6620" />
<img width="1440" height="1024" alt="Silicium - App Dashboard(1)" src="https://github.com/user-attachments/assets/ca8d55f1-7cef-4b67-8bab-c933ba00e325" />
<img width="1440" height="1024" alt="Silicium - App Dashboard" src="https://github.com/user-attachments/assets/817fa73e-08b2-4b49-a86a-11a5b4322707" />       

### Notice
Not yet convince about the user Dashboard, currently too "raw" and too big elements.
