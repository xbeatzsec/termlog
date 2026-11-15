# Source from .zshrc. Only Terminator tabs participate in automatic logging.
if (( ! $+functions[termlog] )); then
  typeset -gx TERMLOG_ZSH_LOADED=1
  typeset -g TERMLOG_COMMAND=${TERMLOG_COMMAND:-${${(%):-%x}:A:h}/termlog}
  function termlog() {
    case ${1:-} in
      disable) export TERMLOG_DISABLED=1; print '[termlog] Automatic integration disabled in this shell.' ;;
      enable) unset TERMLOG_DISABLED; print '[termlog] Automatic integration enabled in this shell.' ;;
      *) command "$TERMLOG_COMMAND" "$@" ;;
    esac
  }
fi
if [[ -o interactive && -t 0 && -t 1 && -n ${TERMINATOR_UUID:-} && ${TERMLOG_INITIALIZED:-} != "$TERMINATOR_UUID" ]]; then
  export TERMLOG_INITIALIZED=$TERMINATOR_UUID
  if [[ -z ${TERMLOG_ACTIVE:-} && -z ${TERMLOG_DISABLED:-} && ${TERMLOG_MODE:-ask} != off ]]; then
    if command "$TERMLOG_COMMAND" _active 2>/dev/null; then
      case ${TERMLOG_MODE:-ask} in
        auto) exec "$TERMLOG_COMMAND" _entry ;;
        ask)
          local reply
          while true; do
            printf '[termlog] An active logging session was detected.\n[termlog] Start logging in this terminal? [Y/n]: '
            if ! read -r reply; then break; fi
            case ${reply:l} in
              ''|y|yes|s|sim) exec "$TERMLOG_COMMAND" _entry ;;
              n|no|não|nao) break ;;
            esac
          done ;;
      esac
    fi
  fi
fi
