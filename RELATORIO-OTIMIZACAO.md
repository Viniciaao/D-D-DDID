# Random Events Project — Análise e Otimização dos Scripts

Data: 2026-09-13 · Branch: `arena/01a0988b-d-d-ddid`

## Metodologia

Para otimizar com garantia de correção, foi construído um **compilador SCM próprio**
(`tools/sbcompile.py`) que reproduz o comportamento do Sanny Builder 3 para o subconjunto
de sintaxe usado pelo mod. Validação: **os 20 binários distribuídos (.cs/.qa) foram
reproduzidos byte-a-byte** a partir dos .txt originais (única diferença admissível: bytes
de lixo após o NUL em strings GXT, que o jogo ignora). Só depois os fontes foram
otimizados e recompilados, e cada binário otimizado foi comparado instrução-a-instrução
com o original para garantir que **apenas as mudanças pretendidas** foram introduzidas.

## Análise geral

Estrutura do mod: script principal (`Random Events Project.cs`, 822 instruções) faz o
despacho dos 17 eventos por proximidade (raio `radius_start`), mais `preqa6`/`r5cut`
(cenas auxiliares). Cada evento (`repqa1..17.qa`) roda como script CLEO próprio, com o
padrão: setup (models/atores/veículos) → loop de gameplay `wait 0` → encerramento com
gravação de progresso em `cleo\Progress.ini`.

Pontos avaliados como **já eficientes** (não alterados):
- Loop principal com `wait 100` e checagens de distância O(1) — custo desprezível a 10 Hz.
- Loops de eventos com `wait 1000` para reler o INI de progresso.
- `gosub @Reward_1_2` no loop principal: só executa 1 vez (bits são limpos ao final);
  os `wait 250` entre leituras de INI são intencionais.
- Os 64 `NOP` de `:Buffer` em `repqa1` são um **buffer de dados** usado via
  `get_label_pointer`/`write_struct_offset` — intocados.
- Coronas por frame em `repqa2:@Light_Obj`, `038B` one-shot, `wait 0` de gameplay
  (responsividade de animações/AS) — mantidos.

## Otimizações aplicadas (repqa1–repqa17)

### 1. Remoção de `gosub @Coords` por frame nos loops principais
O subroutine `@Coords` apenas atribui constantes (dependem só do parâmetro `0@` do
evento), mas era chamado **a cada frame** (`wait 0`) no fim do loop principal de todos
os eventos: gosub + comparação + 4 atribuições + return, milhares de vezes por minuto
durante um evento ativo, sem efeito algum. A chamada única de setup (antes do loop)
já inicializa tudo. Removida a chamada por-frame em 17 scripts (2 em repqa16/repqa17).

Caso especial — `repqa13`: a chamada de setup original só executa quando `Progress`
avança para 1, mas a condição de saída do loop usa as coordenadas desde o início.
Foi adicionada uma chamada única `gosub @Coords` antes do loop (preservando o
comportamento original, que dependia da chamada por-frame para isso).

### 2. Loops de espera de áudio no encerramento: `wait 0` → `wait 100`
Padrão `repeat wait 0 0AB9: get_audio_stream ... until == -1` — polling em frame-rate
cheio esperando a linha de voz terminar (segundos), no fim do script. Com `wait 100`
o polling fica 60× mais leve; o único efeito é até 100 ms a mais antes de liberar o
stream já terminado. Aplicado em: repqa1 (×2), repqa2, repqa3, repqa5, repqa6, repqa7,
repqa8, repqa9, repqa11, repqa12, repqa14, repqa15, repqa16 (×2), repqa17 (×2).

### 3. Subroutine `:Sound` (efeito sonoro .wav): `wait 0` → `wait 50`
Os dois loops de polling (`load_wav` até carregar; `wav ended` até terminar) giravam a
frame-rate cheio durante todo o efeito sonoro (~1 s). Com `wait 50`, latência máxima
adicional de 50 ms no início/fim do efeito — imperceptível. Aplicado em 13 scripts:
repqa1, repqa2, repqa4, repqa5, repqa6, repqa7, repqa8, repqa12, repqa13, repqa14,
repqa15, repqa16, repqa17.

## Verificação dos binários otimizados

Cada `.qa` otimizado foi comparado instrução-a-instrução com o original: as únicas
diferenças são exatamente as pretendidas (remoção dos `gosub @Coords` por-frame,
constantes de `wait` alteradas, e labels deslocadas em consequência). Zero diferenças
inesperadas nos 17 scripts. Os fontes `.txt` correspondentes foram atualizados; os
binários recompilados embutem o novo fonte no trailer SRC, como o Sanny Builder faz.

Scripts **não modificados**: `Random Events Project.txt/.cs`, `preqa6`, `r5cut`.

## Como recompilar

Veja `tools/README.md`. Resumo:

```sh
export SCM_SA_DIR=/caminho/para/sannybuilder-data/sa
python3 tools/sbcompile.py "cleo/repqa1.txt" cleo/repqa1.qa
python3 tools/disasm.py cleo/repqa1.qa   # inspecionar
```

Recompilar qualquer .txt **não modificado** deste repositório reproduz o binário
distribuído byte-a-byte — o que atesta a fidelidade do compilador.
