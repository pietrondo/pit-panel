Istruzione Operativa per Jules: Miglioramento Incrementale Mypy
Obiettivo
Migliorare la robustezza e la manutenibilità del codice di pit-panel aggiungendo i Type Hints mancanti e risolvendo i warning di Mypy in modo incrementale (un solo file o modulo per sessione lavorativa).

Frequenza ed Ambito
Frequenza: Una volta al giorno (o una volta per esecuzione).

Ambito: Esclusivamente i file Python contenuti nella directory src/pit_panel/.

Protocollo di Esecuzione (Step-by-Step)
1. Selezione del Target
Ispeziona la directory src/pit_panel/ e identifica un file Python che:

Non sia ancora completamente tipizzato (mancano definizioni nei parametri delle funzioni o nei tipi di ritorno).

Oppure generi errori/warning quando viene eseguito il controllo dei tipi tramite patch_system_mypy.py.

Scegli un solo file per sessione. Non estendere la modifica a più file contemporaneamente.

2. Configurazione dell'Ambiente di Lavoro
Prima di apportare modifiche, assicurati di lavorare su un branch isolato e pulito.

Nomina il branch seguendo questa convenzione: jules/fix-mypy-[nome-del-file].

3. Analisi e Refactoring
Analizza il file selezionato.

Inserisci i Type Hints appropriati (str, int, dict, Optional, Any, ecc.), prestando particolare attenzione alle strutture dati che gestiscono le configurazioni delle app e i flussi di Docker Compose.

Risolvi i warning di Mypy esistenti senza alterare la logica di business o il comportamento a runtime del codice.

4. Validazione e Test
Esegui lo script di controllo presente nel repository per verificare la conformità:

Bash
uv run python patch_system_mypy.py
Se lo script rileva nuovi errori nel file modificato o regressioni nei moduli correlati, correggi i tipi finché il controllo non si completa con successo.

Assicurati che l'applicazione continui a avviarsi correttamente senza errori di sintassi.

5. Output e Consegna