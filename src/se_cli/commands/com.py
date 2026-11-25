"""Escape genérico a COM: `se com get|set|invoke` y `se run` (scripts, bloqueado por defecto)."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import sin_dialogos
from se_cli.core import com, script
from se_cli.ejecucion import ejecutar

app = typer.Typer(
    help="Acceso directo a la API COM desde la Application: ActiveDocument.Name, "
    "Documents.Item(1).Name. Parser estricto, sin eval.",
    no_args_is_help=True,
)

RutaArgumento = Annotated[
    str,
    typer.Argument(
        help="Ruta desde la Application: segmentos con punto y llamadas con literales "
        "(Documents.Item(1).Name)."
    ),
]


def _plan(accion: str, ruta: str, **extra: Any) -> dict[str, Any]:
    segmentos = com.parsear_ruta(ruta)
    com.rechazar_prohibidos(segmentos)
    return {
        "accion": accion,
        "ruta": com.texto_de_ruta(segmentos),
        "segmentos": [s.nombre for s in segmentos],
        **extra,
    }


@app.command("get")
def obtener(
    ctx: typer.Context,
    ruta: RutaArgumento,
    listar: Annotated[
        bool, typer.Option("--list", help="Si es una colección, listá sus ítems (con Name).")
    ] = False,
    limit: Annotated[
        int, typer.Option("--limit", help="Máximo de ítems con --list.")
    ] = com.LIMITE_POR_DEFECTO,
) -> None:
    """Leé una propiedad. Un objeto COM sale como {tipo, repr, nombre}; no enumera solo."""

    def correr(sesion):
        segmentos = com.parsear_ruta(ruta)
        return sesion.llamar(lambda app: com.obtener(app, segmentos, listar=listar, limite=limit))

    ejecutar(ctx, correr, plan=lambda: _plan("com.get", ruta))


@app.command("set")
def asignar(
    ctx: typer.Context,
    ruta: RutaArgumento,
    valor: Annotated[str, typer.Argument(help='Literal: 10, 0.5, "texto", true, false o null.')],
) -> None:
    """Asigná una propiedad (modifica: lo bloquea --readonly)."""

    def plan() -> dict[str, Any]:
        return _plan("com.set", ruta, valor=com.parsear_literal(valor))

    def correr(sesion):
        segmentos = com.parsear_ruta(ruta)
        literal = com.parsear_literal(valor)
        trabajo = lambda app: com.asignar(app, segmentos, literal)  # noqa: E731
        if segmentos[-1].nombre.lower() == "displayalerts":
            # `sin_dialogos` restauraría el valor y deshariá la propia asignación.
            return sesion.llamar(trabajo, reintentar_todo=False)
        return sin_dialogos(sesion, trabajo)

    ejecutar(ctx, correr, modifica=True, plan=plan)


@app.command("invoke")
def invocar(
    ctx: typer.Context,
    ruta: RutaArgumento,
    argumentos: Annotated[
        list[str] | None,
        typer.Argument(help='Argumentos literales sueltos: 1 "texto" true null.'),
    ] = None,
) -> None:
    """Llamá a un método (modifica: lo bloquea --readonly). `Quit` está denegado."""

    def plan() -> dict[str, Any]:
        literales = [com.parsear_literal(a, "El argumento") for a in argumentos or []]
        return _plan("com.invoke", ruta, argumentos=literales)

    def correr(sesion):
        segmentos = com.parsear_ruta(ruta)
        literales = tuple(com.parsear_literal(a, "El argumento") for a in argumentos or [])
        return sin_dialogos(sesion, lambda app: com.invocar(app, segmentos, literales))

    ejecutar(ctx, correr, modifica=True, plan=plan)


def registrar(raiz: typer.Typer) -> None:
    raiz.add_typer(app, name="com")

    @raiz.command("run")
    def correr_script(
        ctx: typer.Context,
        archivo: Annotated[str, typer.Argument(help="Script .py que define main(app, args).")],
        allow_scripts: Annotated[
            bool,
            typer.Option(
                "--allow-scripts",
                help="Permití ejecutar el script: corre con tus permisos y puede hacer cualquier "
                "cosa. Sin este flag `run` siempre falla (exit 6).",
            ),
        ] = False,
        args: Annotated[
            list[str] | None, typer.Argument(help="Argumentos para main (después de --).")
        ] = None,
    ) -> None:
        """Ejecutá un script Python con la Application (bloqueado salvo --allow-scripts)."""
        lista = list(args or [])
        ejecutar(
            ctx,
            lambda sesion: sesion.llamar(
                lambda app: script.ejecutar(app, archivo, lista), reintentar_todo=False
            ),
            modifica=True,
            con_plazo=False,
            plan=lambda: script.planificar(archivo, lista, allow_scripts),
        )
