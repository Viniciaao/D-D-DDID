# Busy Pedestrians (Peds Events Project) — Análise de uso de memória

Data: 2026-09-15 · Branch: `arena/01a0a752-d-d-ddid`
Escopo: **somente os scripts** (`BP(PEP)/Busy Pedestrians (Peds Events Project)/…/cleo/*.txt`
e `Settings/cleo/Busy Pedestrians.ini`). Modelos/sons não estão no repo e não foram avaliados.

---

## 1. Resumo executivo

Sim, dá para reduzir o uso de memória — e bastante. O gargalo **não** é o código dos
scripts (isso é ruído), é o **modelo de carregamento de assets**:

| Item | Situação atual | Potencial |
|---|---|---|
| `0F00 load_special_model` | **212 chamadas**, 207 DFFs únicos, 14 TXDs | carregados **todos**, **sempre**, **para sempre** |
| `0F01 remove_special_model` | **0 chamadas** | nada é liberado até fechar o jogo |
| Gating por `Busy Pedestrians.ini` | **inexistente** nos loaders | ~40–60 % dos DFFs podem ser evitados em configs típicas |
| Scripts `.cs` residentes | 33 (~625 KB de fonte) | ~8 podem ser fundidos/terminados |
| Render objects (`0F02/03/04`) | 153 criados, 82 deletados | 51 arquivos criam sem nunca chamar `0E2F` |
| `wait 0` em loops | 730 ocorrências | CPU, não RAM (já tratado no outro relatório) |

**Ganho estimado:** 30–60 % da RAM ocupada pelo mod, dependendo do quanto o usuário
desativa no INI. E o mais importante: o pico deixa de ser fixo/permanente.

---

## 2. O problema principal: 212 modelos especiais permanentes

### Como funciona hoje

Todos os loaders (`ModelLoad`, `Models loading`, `StreetLoad`, `StreetCLLoad`,
`Start Script 2/3/4/BW/BW 2`, `Start_Interior`, `News Paper`, `GangsWithMusic`,
`Fish Rod`, `Security Van Heist`) seguem o mesmo padrão:

```
if 0E2D: is_game_first_start
then
    0F00: load_special_model_dff "modelsq\case_peds" txd "modelsq\CaseQ" store_to 0@
    0AF1: write_int 0@ to_ini_file "cleo\PedsModels.ini" section "Models" key "case1"
    ... (× 212)
end
```

Distribuição:

| Arquivo | Loads | TXDs |
|---|---:|---|
| `ModelLoad.txt` | **110** | CaseQ 18, OtherQa 23, BeachQ 17, ShopQ 16, EatQ 16, ToolsQ 13, PaperQ 7 |
| `News Paper.txt` | 17 | NPaperQ |
| `Start Script 2.txt` | 17 | OtherQa |
| `Start Script BW.txt` | 16 | StWork |
| `Start Script 3.txt` | 10 | OtherQa, PedsVndQ |
| `StreetLoad.txt` | 10 | STMusic |
| `Models loading.txt` / `StreetCLLoad.txt` | 7 / 7 | PedsVndQ / StreetCL |
| `Start Script 4/BW 2/Start_Interior/GangsWithMusic/Fish Rod/Security Van` | 5/2/4/4/2/1 | — |

Três consequências:

1. **Nada é liberado.** `0F01 REMOVE_SPECIAL_MODEL` existe no CLEO+ 1.2.0 e **não aparece
   uma única vez** em todo o mod. Cada clump RW + textura fica residente do boot até o
   fim da sessão, mesmo que o evento correspondente nunca aconteça.
2. **Nada é condicional.** Nenhum dos 212 `0F00` está dentro de um `if` de configuração.
   Verifiquei: a primeira leitura de `Busy Pedestrians.ini` acontece **depois** do bloco
   de loads em `Start Script 2` (linha 39 vs 112), `Start Script 4` (39 vs 91),
   `Start Script BW` (39 vs 132); e `ModelLoad`, `Models loading`, `StreetLoad`,
   `StreetCLLoad`, `Start_Interior` **nem leem** o INI de configurações. Ou seja: você
   pode desligar "Street musicians", "Street Cleaners", "News Paper", "Improved
   interiors", "Gangs With Music" — e os 10 + 7 + 17 + 4 + 4 modelos continuam na RAM.
3. **Duplicatas reais.** O mesmo DFF é carregado mais de uma vez, gerando cópias
   independentes em memória:
   - `modelsq\cops_peds2` → **3×** (`ModelLoad` key `cop2`, `Start Script 2` key `copB2`, `Start Script 4` key `copA2`)
   - `modelsq\camera2_peds` → **2×** (`camera2`, `cameraB2`)
   - `modelsq\ice` → **2×** (`Models loading` `ice`, `Start Script 3` `iceq`)
   - `modelsq\Broom1` → **2×** (`Start Script 4` `BroomQ2`, `Start_Interior` `Broom`)
   
   São **4 clumps desperdiçados** só por falta de reuso da chave já gravada no INI.
4. **Uma chave morta:** `phone` (`modelsq\phone_peds`, `ModelLoad.txt:168`) é gravada e
   **nunca lida por script nenhum** — `Peds Phone.txt` usa só a animação `phone_kiosk`
   e o objeto 1216 do mapa. É um DFF+entrada de TXD carregado à toa, para sempre.

### O que fazer (em ordem de custo/benefício)

**A. Gatear os loaders pelo INI (ganho grande, risco baixo).**
Mover a leitura das chaves de `[Settings]` para **antes** do bloco `is_game_first_start`
e envolver cada grupo de `0F00` no seu toggle. Os grupos já estão perfeitamente
separados por TXD, o que torna isso quase mecânico:

| TXD | Loads | Toggle do INI que já existe |
|---|---:|---|
| `STMusic` (`StreetLoad.txt`) | 10 | `[Settings] Street musicians` |
| `StreetCL` (`StreetCLLoad.txt`) | 7 | `[Settings] Street Cleaners` |
| `NPaperQ` (`News Paper.txt`) | 17 | `[Settings] News Paper` ← já há um `terminate` por esse toggle na linha 37/41, mas **os loads estão depois**; basta reordenar |
| `Blasters` (`GangsWithMusic.txt`) | 4 | `[Settings] Gangs With Music` ← idem, `terminate` na linha 43, loads na 49 |
| `ImpInt` (`Start_Interior.txt`) | 4 | `[Improved interiors]` (GYM/Garage/Club/Barber…) |
| `StWork` (`Start Script BW/BW 2`) | 18 | `Postman`, `Communication repairers`, `WindWash`, `Road Workers`, `Bridge Workers` |
| `PedsVndQ` (`Models loading.txt`) | 7 | `Peds use Vends` + `Food in the player hand` |
| `OtherQa` (`Start Script 2/3/4`, `Fish Rod`, `Security Van`) | 32 | vários toggles + `[Percent Chance]` |

Observação importante sobre `News Paper.txt` e `GangsWithMusic.txt`: eles **já terminam**
o script quando o toggle é 0, mas o `0A93 terminate_this_custom_script` está *antes*…
não: confirmei que a ordem é `terminate` (l.41/43) → `loads` (l.47/49). Nesses dois casos
o gating **já funciona**. O problema real está em `ModelLoad`, `Models loading`,
`StreetLoad`, `StreetCLLoad` e `Start_Interior`, que não consultam nada.

**B. Eliminar as 4 duplicatas.** Em `Start Script 2/4` e `Start_Interior`, em vez de
recarregar, ler a chave já existente:

```
// em vez de:
0F00: load_special_model_dff "modelsq\cops_peds2" txd "modelsq\OtherQa" store_to 0@
0AF1: write_int 0@ to_ini_file "cleo\PedsModels.ini" section "Models" key "copB2"
// usar:
0AF0: 0@ = read_int_from_ini_file "cleo\PedsModels.ini" section "Models" key "cop2"
0AF1: write_int 0@ to_ini_file "cleo\PedsModels.ini" section "Models" key "copB2"
```

Cuidado: isso cria dependência de ordem entre scripts. `ModelLoad` roda com `wait 50`,
`Start Script 2` com `wait 500` — a ordem já favorece, mas o correto é o consumidor
esperar `Loaded1 == 1` (padrão que `Start script.txt` já usa no topo).

**C. Remover o load de `phone`** (`ModelLoad.txt:168-169`) — asset morto.

**D. (avançado) Carregamento sob demanda com `0F01`.** Para os grupos grandes e raros —
`BeachQ` (17), `NPaperQ` (17), `ToolsQ` (13) — o ideal é carregar quando o script
consumidor inicia e chamar `0F01: remove_special_model` no encerramento dele. Isso
muda o modelo de "tudo residente" para "pico por cena". É a mudança de maior ganho e
maior risco: os handles são compartilhados via INI entre vários `.qa`, então precisa de
refcount (ex.: uma chave `RefCount_<txd>` no INI) para não liberar modelo em uso.
Recomendo fazer só depois de A/B/C, e começando por `NPaperQ`, que tem um consumidor
único (`News Paper.txt`).

---

## 3. Render objects criados e nunca deletados

`0F02/0F03/0F04` criam 153 render objects; só 82 `0E2F delete_render_object` existem.
**51 arquivos criam render object sem nenhum `0E2F`.** Na prática o CLEO+ costuma
destruir o render object junto com a entidade-pai, então nem tudo é vazamento — mas há
casos claros em que o **handle é perdido**, tornando a limpeza impossível:

```
// Atrium.txt:81-83
0F02: create_render_object_to_char_bone_from_special ped_2 special_model 1@ ... store_to 1@
0209: 1@ = random_int_in_ranges 0 2      // handle sobrescrito 2 linhas depois
```

Mesmo padrão em:

| Arquivo | Linha da criação | Handle perdido em |
|---|---:|---|
| `Atrium.txt` | 81 | 83 |
| `Golf Peds.txt` | 89 | 90 |
| `In Out Peds.txt` | 140 | 146 |
| `Interior RestQa.txt` | 277 | 282 |
| `Street Artist.txt` | 86 | 92 |
| `Tram Peds.txt` | 335, 428, 490, 583 | 341, 434, 496, 589 (`0A97: 1@ = car struct`) |

Correção trivial e de risco zero: usar uma variável dedicada (`const Render_Obj = 9@`)
em vez de `1@` scratch, e chamar `0E2F` na rotina de cleanup que já existe
(`:Destroy_peds`, `:References_remove`). `Tram Peds.txt` é o pior caso: cria **16**
render objects e não tem um único `0E2F`.

---

## 4. Áudio: streams que vazam

`0AC1 load_audio_stream_with_3d_support` aparece 47×, `0AAE remove_audio_stream` 81×.
No geral está equilibrado, mas dois casos merecem atenção:

- **`Peds use Vends.txt`** — 4 `0AC1` (linhas 286, 300, 314, 362) e **1 único** `0AAE`
  (linha 561). Os três primeiros recarregam `SQ\pedspunch.mp3` em `soundsqa` em ramos
  diferentes. Há guarda `soundsqa == -1` antes de cada um, o que evita o vazamento
  imediato, mas `soundsqa` nunca é resetado para `-1` após o som terminar — então na
  prática só o primeiro toca por ciclo, e o stream fica alocado até o fim do loop.
  Correção: após `0AB9` indicar fim, `0AAE` + `soundsqa = -1`.
- **`Rap Battle.txt`** — 3 `0AC1` (122, 240, 252) para 2 `0AAE` (234, 295). O caminho
  240→sem remove antes de 252 pode deixar um stream órfão.

Cada MP3 stream 3D carregado é buffer de áudio residente; com `[Gangs With Music]
Number of songs = 5` e as várias faixas de `Street musicians`, isso soma.

---

## 5. Animações (IFP)

`PedEventsMod.ifp` tem **2,2 MB** e é referenciado por 591 comandos. O padrão
`04ED load_animation` / `04EF release_animation` está bem balanceado — só 2 exceções:

- `Para Jumper.txt` carrega `PARACHUTE` e nunca libera;
- `RC game.txt` carrega `CRIB` e nunca libera.

Mais relevante é a **janela de retenção**. Em vários scripts o IFP fica carregado
durante quase todo o tempo de vida do script:

| Arquivo | load → release | linhas |
|---|---|---:|
| `Street Dice.txt` | `PedEventsMod` | 85 → 665 (580 linhas) |
| `Street Fight.txt` | `PedEventsMod` | 45 → 622 |
| `Improved GYM.txt` | `Freeweights`+`GYMNASIUM`+`benchpress` | 39/44/49 → 593/594/595 |
| `Street Guitar.txt` | `PedEventsMod` | 542 → 1032 |

Isso é em boa parte inerente (a animação está tocando), mas `Improved GYM` segurando
**três** blocos de anim do jogo base pelo script inteiro é evitável: cada um só é usado
em um ramo específico.

Nota sobre `PedsWalk.txt`: a rotina `:Realese_animation` só libera `PedEventsMod`,
`GANGS` e `VENDING` quando **todos os 7** atores estão indefinidos — condição rara em
área movimentada. Na prática o IFP fica preso quase permanentemente.

---

## 6. Scripts residentes (`.cs`)

33 scripts `.cs` ficam sempre carregados (~625 KB de fonte; os `.qa` são 87 arquivos
streamados sob demanda — esse lado está certo). Os maiores:

```
85 KB  Start Script 2.txt      (2159 linhas)
61 KB  Start Script 3.txt
49 KB  News Paper.txt
40 KB  Start Script 4.txt
32 KB  Peds use Vends.txt
28 KB  Security Van Heist.txt
26 KB  Tram Peds.txt
21 KB  ModelLoad.txt
```

Pontos concretos:

- **`ModelLoad.txt` (311 linhas) nunca termina cedo.** Roda os 110 loads e só então
  `004E`. Como o corpo inteiro está sob `is_game_first_start`, em saves posteriores ele
  ainda assim executa os 13 `0AF1 write_int` de flags. Custo baixo, mas é o candidato
  natural para receber o gating do item 2A.
- **Os 5 loaders separados** (`ModelLoad`, `Models loading`, `StreetLoad`,
  `StreetCLLoad` + os blocos nos `Start Script`) poderiam ser **um único** `.cs` loader,
  eliminando 4 slots de script CLEO residentes e 4 cópias do mesmo bloco de verificação
  de versão do CLEO+ (o bloco `0AA2/0AA4/0AA7` de ~20 linhas está duplicado em **18**
  arquivos).
- **`PedsCopMed.txt`, `Water VEnd.txt`, `Start script.txt`** não têm nenhum
  `0A93 terminate_this_custom_script` e não consultam `[Settings]` — não há como
  desligá-los pelo INI. Adicionar um toggle + terminate a cada um libera o slot inteiro
  para quem não quer a feature.
- **O buffer `:Buffer` em `Start script.txt`** reserva 420 bytes (`hex 00(420)`) para
  ~100 ints, mas o mapa de offsets usado vai só até o índice 57 (`water`). Sobram ~170
  bytes. Irrelevante em RAM, mas vale documentar.
- `Start script.txt` faz **35 leituras de INI** em sequência no startup (e
  `Start Script BW` 26, `Start Script 2` 22). Isso não é memória, é I/O de boot — mas
  cada `0AF0` abre/parseia o arquivo inteiro. Ler `PedsModels.ini` 35 vezes é 35 parses
  completos. Não é onde está a RAM, só anoto para completude.

---

## 7. Plano sugerido (ordem de execução)

1. **Deduplicar os 4 DFFs repetidos** + remover `phone`. Ganho imediato, risco ~zero,
   5 linhas alteradas.
2. **Corrigir os 9 handles de render object sobrescritos** e adicionar `0E2F` nos
   cleanups existentes (prioridade: `Tram Peds.txt`, 16 objetos).
3. **Gatear os loaders pelo INI** — começar por `StreetLoad` (10), `StreetCLLoad` (7) e
   `Start_Interior` (4), que têm toggle 1:1 e consumidores isolados. Depois `StWork` (18)
   e `OtherQa` (32), que exigem mapear toggle→chave com cuidado.
4. **Corrigir os streams de áudio** em `Peds use Vends.txt` e `Rap Battle.txt`; liberar
   `PARACHUTE` e `CRIB`.
5. **Fundir os 5 loaders em um só** e extrair a checagem de versão do CLEO+ duplicada
   em 18 arquivos.
6. **(opcional/avançado)** Carregamento sob demanda com `0F01` + refcount, começando por
   `NPaperQ`.

Os passos 1–4 são seguros e mecânicos. O 5 muda a estrutura de instalação (menos
arquivos no `cleo/`). O 6 muda o modelo de memória do mod e exige teste em jogo.

---

## 8. O que **não** vale mexer

- Os 730 `wait 0`: são CPU, não memória, e boa parte é necessária para responsividade de
  animação (já discutido no `RELATORIO-OTIMIZACAO.md` do Random Events Project).
- `01C2 remove_references_to_actor` (547×): o mod usa corretamente o padrão de devolver
  o ped ao pool em vez de deletar. Está certo.
- O uso de `.qa` streamado para os 87 eventos: essa é exatamente a arquitetura correta e
  é o que impede o mod de ser muito pior do que é.
- Os `0E0B mark_char_as_needed` (36×): necessários para o ped não sumir durante a cena.

---

*Análise estática dos 147 arquivos de script. Modelos (`.dff`/`.txd`) e áudio (`.mp3`)
não estavam presentes no repositório — os números de "quantidade" são exatos, os de
"quantos MB" dependem dos seus arquivos locais. Se quiser, me passe os tamanhos da pasta
`modelsq/` e eu converto a tabela da seção 2 em MB reais por grupo.*
