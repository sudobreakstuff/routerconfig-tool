from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.connection import get_session
from models.config_template import ConfigTemplate
from core.templates import BUILTIN_TEMPLATES, parse_template, render_commands

router = APIRouter()


@router.get("")
async def list_templates(
    vendor: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ConfigTemplate)
    if vendor:
        stmt = stmt.where(ConfigTemplate.vendor == vendor)
    result = await session.execute(stmt.order_by(ConfigTemplate.name))
    db_templates = result.scalars().all()

    templates = [{
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "vendor": t.vendor.value if t.vendor else "any",
        "config_commands": t.config_commands,
        "jinja2_template": t.jinja2_template,
        "variables_schema": t.variables_schema,
        "is_default": t.is_default,
        "version": t.version,
        "source": "custom",
    } for t in db_templates]

    for key, bt in BUILTIN_TEMPLATES.items():
        if not vendor or bt.get("vendor") == vendor or bt.get("vendor") == "generic":
            templates.append({
                "id": key,
                "name": bt["name"],
                "description": bt.get("description", ""),
                "vendor": bt.get("vendor", "any"),
                "config_commands": bt.get("config_commands", []),
                "is_default": bt.get("is_default", False),
                "source": "builtin",
            })

    return templates


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    session: AsyncSession = Depends(get_session),
):
    if template_id in BUILTIN_TEMPLATES:
        bt = BUILTIN_TEMPLATES[template_id]
        return {
            "id": template_id,
            "name": bt["name"],
            "description": bt.get("description", ""),
            "vendor": bt.get("vendor", "any"),
            "config_commands": bt.get("config_commands", []),
            "jinja2_template": bt.get("jinja2_template"),
            "variables_schema": bt.get("variables_schema"),
            "is_default": bt.get("is_default", False),
            "source": "builtin",
            "variables": [{"name": v.name, "label": v.label, "type": v.type, "required": v.required}
                          for v in parse_template("\n".join(bt.get("config_commands", [])))],
        }

    result = await session.execute(select(ConfigTemplate).where(ConfigTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "vendor": template.vendor.value if template.vendor else "any",
        "config_commands": template.config_commands,
        "jinja2_template": template.jinja2_template,
        "variables_schema": template.variables_schema,
        "is_default": template.is_default,
        "version": template.version,
        "source": "custom",
        "variables": [{"name": v.name, "label": v.label, "type": v.type, "required": v.required}
                      for v in parse_template("\n".join(template.config_commands or []))],
    }


@router.post("")
async def create_template(
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    template = ConfigTemplate(**data)
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return {"id": template.id, "name": template.name}


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(ConfigTemplate).where(ConfigTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    for key, val in data.items():
        if hasattr(template, key) and key != "id":
            setattr(template, key, val)

    template.version += 1
    await session.commit()
    return {"id": template.id, "name": template.name, "version": template.version}


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import delete
    await session.execute(delete(ConfigTemplate).where(ConfigTemplate.id == template_id))
    await session.commit()
    return {"success": True}


@router.post("/preview")
async def preview_template(
    data: dict,
):
    commands = data.get("commands", data.get("config_commands", []))
    variables = data.get("variables", {})
    jinja2_template = data.get("jinja2_template")

    if jinja2_template:
        rendered = render_commands(jinja2_template, variables)
    elif isinstance(commands, list):
        rendered_commands = []
        for cmd in commands:
            rendered_cmd = cmd
            for key, val in variables.items():
                rendered_cmd = rendered_cmd.replace(f"${{{key}}}", str(val))
                rendered_cmd = rendered_cmd.replace(f"{{{{{key}}}}}", str(val))
            rendered_commands.append(rendered_cmd)
        from core.templates import RenderedConfig
        rendered = RenderedConfig(commands=rendered_commands, variables_used=variables)
    else:
        rendered = render_commands(str(commands), variables)

    return {
        "commands": rendered.commands,
        "variables_used": rendered.variables_used,
    }
