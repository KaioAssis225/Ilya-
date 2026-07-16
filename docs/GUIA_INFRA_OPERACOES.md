# Guia de infraestrutura e operações - Projeto Ilya

Versão 2.0 - 14/07/2026

Este guia separa claramente o ambiente local do ambiente de produção. Comandos
do Docker local não protegem automaticamente o PostgreSQL ou os arquivos do
Railway.

## 1. Estado esperado do ambiente local

Na pasta do projeto, execute:

```powershell
docker --version
docker compose version
docker compose ps
```

Os serviços `ilya_backend` e `ilya_db` devem aparecer como ativos, e o banco
deve estar saudável. Confirme a API:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

O `docker-compose.yml` atual contém banco e backend, mas não contém o frontend.
Para desenvolvimento local, execute o frontend separadamente:

```powershell
cd frontend
npm install
npm run dev
```

Depois, acesse `http://localhost:5173`. A documentação em
`http://localhost:8000/docs` só existe com `DEBUG=true`.

## 2. Segredos

- Nunca envie `.env`, URL do PostgreSQL ou senhas por e-mail, chat ou Git.
- Use uma senha exclusiva para criptografar os backups.
- Guarde essa senha em um cofre externo. Sem ela, arquivos `.enc` não podem ser
  restaurados.
- O arquivo `.secrets/backup-secrets.json` usa DPAPI: somente o mesmo usuário do
  Windows, no mesmo computador, pode abri-lo.

Configure os segredos operacionais:

```powershell
.\ops\set-backup-secrets.ps1
```

O procedimento solicita:

1. URL pública do PostgreSQL de produção.
2. Senha exclusiva de criptografia.
3. Usuário administrador para exportação lógica da API.
4. Senha desse usuário.
5. Pasta externa sincronizada, como OneDrive, rede ou disco externo.

## 3. Backup do banco local

O comando abaixo cria um dump em formato PostgreSQL customizado, verifica o
catálogo e restaura o resultado em um container descartável:

```powershell
.\ops\backup-local.ps1
```

O banco em uso não é alterado. Os arquivos ficam em `backups/database/`, pasta
ignorada pelo Git.

## 4. Backup completo de produção

Execute manualmente uma primeira vez:

```powershell
.\ops\backup-production.ps1
```

A rotina executa, nesta ordem:

1. `pg_dump` do PostgreSQL de produção.
2. Validação do catálogo do dump.
3. Criptografia AES-256 com PBKDF2.
4. Cálculo SHA-256.
5. Restauração em PostgreSQL temporário e isolado.
6. Exportação lógica das entidades pela API.
7. Download das fotos referenciadas pela API.
8. Manifesto com contagens, falhas e hashes dos arquivos.
9. Cópia dos artefatos criptografados para a pasta externa.

O dump PostgreSQL é a fonte de verdade. A exportação da API é uma segunda camada
para inspeção e recuperação seletiva.

### Limitação das fotografias

A exportação lógica baixa todas as fotos referenciadas pelos registros da API.
Ela não consegue detectar arquivos órfãos existentes no volume do Railway.
Para cobertura integral, mantenha também snapshot ou exportação do volume pelo
mecanismo suportado pelo provedor e teste a recuperação desse volume.

## 5. Retenção

As rotinas locais mantêm automaticamente:

- todos os backups dos últimos 7 dias;
- um backup de cada uma das últimas 4 semanas;
- um backup de cada um dos últimos 6 meses.

A limpeza só ocorre depois que um novo backup válido foi criado. Não use a
pasta do próprio projeto como única cópia: falha ou roubo do computador também
eliminaria os backups locais.

## 6. Automação diária no Windows

Depois que o backup manual de produção for aprovado, instale a tarefa:

```powershell
.\ops\install-backup-task.ps1
```

A tarefa `Projeto Ilya - Backup de Producao` roda diariamente às 02:00, começa
assim que possível se o computador estava desligado e não inicia uma segunda
cópia enquanto a primeira estiver em execução.

Antes do backup, a rotina verifica o Docker Engine. Se estiver parado, inicia o
Docker Desktop em segundo plano e aguarda até quatro minutos. A tarefa também
está configurada para despertar o computador quando o Windows permitir. O
computador precisa estar ligado à energia, conectado à internet e não pode estar
completamente desligado.

Para testar imediatamente:

```powershell
Start-ScheduledTask -TaskName "Projeto Ilya - Backup de Producao"
Get-ScheduledTaskInfo -TaskName "Projeto Ilya - Backup de Producao"
```

`LastTaskResult` igual a `0` representa sucesso.

## 7. Restauração segura

Nunca teste uma restauração sobre produção. Para validar um arquivo já criado:

```powershell
$env:BACKUP_ENCRYPTION_PASSWORD = "senha obtida no cofre"
py -3.12 .\ops\test_restore.py .\backups\database\arquivo.dump.enc
Remove-Item Env:BACKUP_ENCRYPTION_PASSWORD
```

O script cria um PostgreSQL temporário, restaura o dump, confirma que existem
tabelas e remove o container mesmo se ocorrer erro.

Uma restauração real de produção exige janela de manutenção, backup imediatamente
anterior, banco de destino vazio, validação funcional e autorização do responsável.
Não use redirecionamento direto com `psql` sobre o banco existente.

## 8. Senha do administrador

Alterar `ADMIN_PASSWORD` no `.env` e executar `seed_admin.py` não redefine um
usuário existente. O seed é idempotente e encerra ao encontrar o e-mail.

Use a função administrativa de redefinição de senha na tela de usuários. Ela
aplica a política de senha e exige troca no próximo acesso. Se nenhum
administrador consegue entrar, solicite ao desenvolvedor um procedimento
controlado; não edite hashes diretamente no banco.

## 9. Monitoramento

Verificação local:

```powershell
docker compose ps
docker compose logs backend --tail 100
Invoke-RestMethod http://localhost:8000/health
```

Verifique semanalmente:

- execução da tarefa e código de saída;
- existência do arquivo `.enc` e do `.sha256` na cópia externa;
- espaço livre local e externo;
- alertas e métricas do provedor;
- validade das credenciais operacionais.

Verifique mensalmente:

- restauração isolada de um backup escolhido aleatoriamente;
- contagem aproximada de tabelas e registros críticos;
- recuperação de uma fotografia;
- acesso à senha de criptografia no cofre externo.

## 10. Incidentes

Em caso de suspeita de invasão, perda ou corrupção:

1. Não apague logs nem arquivos.
2. Registre horário, usuário e ação observada.
3. Revogue sessões e credenciais comprometidas.
4. Preserve uma cópia do banco e dos logs antes de corrigir.
5. Avalie dados pessoais afetados e acione o responsável por LGPD.
6. Restaure somente depois de identificar a causa do incidente.

## 11. Responsabilidades externas

O código não consegue decidir ou executar sozinho:

- contratação e configuração de armazenamento externo;
- política formal de acesso aos backups;
- custódia da senha de criptografia;
- habilitação de snapshots do volume no provedor;
- janela e autorização para restauração de produção;
- plano de continuidade, responsáveis e contatos de emergência;
- avaliação jurídica de incidentes envolvendo dados pessoais.
