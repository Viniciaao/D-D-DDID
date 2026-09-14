# Ferramentas SCM (Random Events Project)

Ferramentas usadas para analisar, validar e recompilar os scripts CLEO/SCM deste mod
(GTA San Andreas). Criadas porque o Sanny Builder não pôde ser executado no ambiente
de otimização; o compilador foi **validado por reprodução byte-a-byte** dos 20 binários
originais (.cs/.qa) a partir dos .txt — ou seja, recompilar o fonte original gera um
binário idêntico ao distribuído.

## Requisitos

- Python 3.8+
- Banco de dados de opcodes do Sanny Builder (repositório `sannybuilder/data`),
  pasta `sa/` contendo: `SASCM.INI`, `SASCM.CLEO.ini`, `SASCM.CLEO+.ini`,
  `SASCM.NewOpcodes.ini`, `SASCM.Clipboard.ini`, `CustomVariables.ini`, `keywords.txt`.

Defina o caminho com a variável de ambiente `SCM_SA_DIR` (padrão: `/tmp/sbdata/sa`):

```sh
export SCM_SA_DIR=/caminho/para/sannybuilder-data/sa
```

## Uso

```sh
# Compilar um fonte .txt para binário (.qa/.cs)
python3 tools/sbcompile.py "cleo/repqa1.txt" cleo/repqa1.qa

# Desmontar um binário para leitura
python3 tools/disasm.py cleo/repqa1.qa
```

O compilador inclui o trailer SB3 (FLAG/SRC/__SBFTR) com o fonte embutido, igual ao
Sanny Builder. Observação: parâmetros GXT (aspas simples) são gravados com zeros após
o NUL; o Sanny Builder gravava lixo de memória nessa região — semanticamente idêntico
(o jogo lê até o NUL).

## Sintaxe suportada

O subconjunto usado pelo mod: `const`/`end`, `if/then/else/end` (and/or, `not`),
`repeat/until`, `while true`, `for ... to ... step`, `break`/`continue`, `gosub`,
`jump`, `return`, labels `:Nome`, variáveis `N@`/`$VAR`/`N@v`, arrays `Nome(idx,Ni)`,
opcodes com prefixo (`0001:`) e mnemônicos (`wait`, `locate_char_distance_to_coordinates`,
`get_ped_pointer`, etc.), class syntax (`model.Load/Destroy/Available`, `player.Defined`),
literais hex, `true/false`, `TIMERA/TIMERB`.
