from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import Selection1688Candidate, SelectionDidadogProduct, SelectionImageSearchEntry, SelectionPipelineKeyword, SelectionPipelineTask
from app.services.pipeline_service import (
    pending_derivation_product_ids,
    pipeline_status,
    run_supplier_match_batch,
)
from app.services.selection_pipeline_service import create_selection_pipeline_task, run_selection_pipeline
from app.services.selection_derivation_service import generate_derivatives_for_product_ids
from app.services.ai_model_service import ModelCallError, chat_completion, extract_json_object


router = APIRouter(
    prefix="/api/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(require_role("admin"))],
)

selection_router = APIRouter(
    prefix="/api/selection-pipeline",
    tags=["selection-pipeline"],
    dependencies=[Depends(require_role("admin", "teacher", "student"))],
)


class DerivationQueueRequest(BaseModel):
    limit: int | None = None
    min_derived_count: int | None = None


class SupplierMatchQueueRequest(BaseModel):
    limit: int | None = None
    threshold: float | None = None
    max_candidates: int | None = None
    page_size: int | None = None


class SelectionPipelineRequest(BaseModel):
    message: str
    mode: str = "selection"
    source_product_id: int | None = None
    region: str = "JP"
    blue_ocean_strategy: str = "comprehensive"


# 蓝海模式支持的市场区域（与 selection_pipeline_service._REGION_LANGUAGE 对齐）
_SUPPORTED_REGIONS = {
    "JP", "US", "GB", "DE", "FR", "IT", "ES", "ID", "MY",
    "TH", "VN", "PH", "SG", "BR", "MX", "IE",
}
_SUPPORTED_STRATEGIES = {"comprehensive", "competition", "competition_growth"}


def _report_product_payload(item: SelectionDidadogProduct) -> dict:
    return {
        "id": item.didadog_product_id,
        "title": item.title or item.didadog_product_id,
        "image_url": item.image_url,
        "price": item.price,
        "currency": item.currency,
        "sales_count": item.sales_count,
        "category": item.category,
        "selection_status": item.selection_status,
    }


def _linked_supplier_items(db: Session, task_id: int, status: str) -> list[dict]:
    """Return the 1688 seed products represented by final EchoTik statuses."""
    candidates = list(db.scalars(select(Selection1688Candidate).where(Selection1688Candidate.pipeline_task_id == task_id).order_by(Selection1688Candidate.id)).all())
    entries = list(db.scalars(select(SelectionImageSearchEntry).where(SelectionImageSearchEntry.pipeline_task_id == task_id)).all())
    products = list(db.scalars(select(SelectionDidadogProduct).where(SelectionDidadogProduct.pipeline_task_id == task_id, SelectionDidadogProduct.selection_status == status).order_by(SelectionDidadogProduct.id)).all())
    candidate_by_id = {item.id: item for item in candidates}
    entry_by_id = {item.id: item for item in entries}
    seen: set[int] = set()
    result: list[dict] = []
    for product in products:
        entry = entry_by_id.get(product.image_search_entry_id)
        supplier = candidate_by_id.get(entry.seed_candidate_id) if entry else None
        if not supplier or supplier.id in seen:
            continue
        seen.add(supplier.id)
        try:
            meta = json.loads(product.selection_meta or "{}")
        except (TypeError, ValueError):
            meta = {}
        result.append({
            "id": supplier.external_product_id or supplier.id,
            "title": supplier.title,
            "image_url": supplier.image_url,
            "price": supplier.price,
            "currency": supplier.currency or "CNY",
            "sales_count": supplier.sales_count,
            "shop_name": supplier.shop_name,
            "source_url": supplier.source_url,
            "selection_status": status,
            "eliminated": False,
            "tier": meta.get("tier", "regular"),
            "novelty_score": meta.get("novelty"),
            "content_score": meta.get("content"),
            "highlight_reason": meta.get("reason", ""),
        })
    return result


@selection_router.post("/tasks/{task_id}/report-content")
def generate_selection_report_content(
    task_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    task = db.get(SelectionPipelineTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="选品任务不存在")
    if user.get("role") != "admin" and int(task.user_id) != int(user.get("id") or 0):
        raise HTTPException(status_code=403, detail="无权导出该选品任务")
    if task.status != "success":
        raise HTTPException(status_code=400, detail="任务尚未完成，暂不能生成报告")
    products = list(db.scalars(select(SelectionDidadogProduct).where(SelectionDidadogProduct.pipeline_task_id == task.id).order_by(SelectionDidadogProduct.id)).all())
    candidates = _linked_supplier_items(db, task.id, "candidate")
    finals = _linked_supplier_items(db, task.id, "final")
    compact = {"需求": task.input_message, "候选品": candidates, "精选品": finals}
    prompt = (
        "你是日本 TikTok 跨境电商资深选品顾问。请根据给定任务结果，生成一份可以直接放进中文选品报告的专业分析。\n"
        "必须只基于输入商品，不要虚构销量、价格、法规结论或市场数据；没有数据就明确写‘需进一步验证’。\n"
        "请严格返回 JSON，不要 Markdown，字段如下：\n"
        "market_summary（200字以内的市场概览）、opportunity_tracks（数组，最多3项，每项包含 track_name、opportunity、reason）、\n"
        "candidate_strategy（候选品布局建议，150字以内）、final_strategy（精选品上架建议，150字以内）、\n"
        "risk_advice（数组，最多5条风险提示）、conclusion（100字以内结论）。\n"
        "分析重点：蓝海逻辑是优先保留销量较低但有需求验证、供应链可做、合规可控的商品；不要把销量高误判为优先推荐。\n"
        f"任务数据：{json.dumps(compact, ensure_ascii=False)}"
    )
    try:
        answer = chat_completion(
            db,
            [{"role": "system", "content": "你负责生成严谨、可落地的电商选品报告内容。"}, {"role": "user", "content": prompt}],
            model_type="general",
            temperature=0.25,
            max_tokens=3000,
        )
        analysis = extract_json_object(answer)
        if not isinstance(analysis, dict):
            analysis = {"market_summary": str(answer)}
    except (ModelCallError, ValueError, TypeError) as exc:
        analysis = {
            "market_summary": "大模型报告分析暂时不可用，以下商品清单仍来自本次已完成任务结果。",
            "opportunity_tracks": [],
            "candidate_strategy": "优先验证候选品的供应链稳定性、成本和短视频素材表现。",
            "final_strategy": "精选品上架前请完成日本法规、限售和专利风险复核。",
            "risk_advice": [f"大模型分析失败：{exc}"],
            "conclusion": "请结合商品清单进行人工复核。",
            "model_error": str(exc),
        }
    return {"task_id": task.id, "candidates": candidates, "finals": finals, "analysis": analysis}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return pipeline_status(db)


@selection_router.post("/tasks")
def create_selection_pipeline(
    payload: SelectionPipelineRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="选品需求不能为空")
    if payload.mode == "derivation" and not payload.source_product_id:
        raise HTTPException(status_code=400, detail="衍生任务缺少原商品 ID")
    if payload.mode == "keyword_blue_ocean":
        region = (payload.region or "JP").strip().upper()
        strategy = (payload.blue_ocean_strategy or "comprehensive").strip() or "comprehensive"
        if region not in _SUPPORTED_REGIONS:
            raise HTTPException(status_code=400, detail=f"暂不支持的市场区域：{region}")
        if strategy not in _SUPPORTED_STRATEGIES:
            raise HTTPException(status_code=400, detail=f"暂不支持的蓝海策略：{strategy}")
        task = create_selection_pipeline_task(
            db, user_id=int(user.get("id") or 0), message=message,
            mode="keyword_blue_ocean", region=region, blue_ocean_strategy=strategy,
        )
    else:
        task = create_selection_pipeline_task(
            db, user_id=int(user.get("id") or 0), message=message,
            mode=payload.mode, source_product_id=payload.source_product_id,
        )
    background_tasks.add_task(run_selection_pipeline, task.id)
    return {"ok": True, "task_id": task.id, "status": task.status, "stage": task.current_stage, "progress": task.stage_progress}


@selection_router.get("/tasks/latest")
def get_latest_selection_pipeline_task(
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    query = select(SelectionPipelineTask).where(SelectionPipelineTask.user_id == int(user.get("id") or 0)).order_by(SelectionPipelineTask.created_at.desc())
    task = db.scalar(query)
    return {"task_id": task.id if task else None}


@selection_router.get("/tasks/{task_id}")
def get_selection_pipeline_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    task = db.get(SelectionPipelineTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="选品任务不存在")
    if user.get("role") != "admin" and int(task.user_id) != int(user.get("id") or 0):
        raise HTTPException(status_code=403, detail="无权查看该选品任务")
    keywords = list(db.scalars(select(SelectionPipelineKeyword).where(SelectionPipelineKeyword.pipeline_task_id == task.id).order_by(SelectionPipelineKeyword.source_index)).all())
    candidates = list(db.scalars(select(Selection1688Candidate).where(Selection1688Candidate.pipeline_task_id == task.id).order_by(Selection1688Candidate.id)).all())
    didadog_products = list(db.scalars(select(SelectionDidadogProduct).where(SelectionDidadogProduct.pipeline_task_id == task.id).order_by(SelectionDidadogProduct.id)).all())
    linked_candidates = _linked_supplier_items(db, task.id, "candidate")
    linked_finals = _linked_supplier_items(db, task.id, "final")
    # 关键词蓝海模式：商品直接落在 SelectionDidadogProduct（无 1688/图搜中间表），
    # 需要据此重建候选/精选与按关键词分组，保证前端看板与报告正常渲染。
    if task.pipeline_mode == "keyword_blue_ocean":
        def _didadog_item(p: SelectionDidadogProduct) -> dict:
            try:
                meta = json.loads(p.selection_meta or "{}")
            except (TypeError, ValueError):
                meta = {}
            eliminated = (
                p.selection_status in {"eliminated", "failed"}
                or p.detail_status in {"failed", "eliminated", "compliance_failed", "restriction_failed"}
            )
            return {
                "id": p.didadog_product_id or f"d-{p.id}",
                "title": p.title or p.didadog_product_id or "未命名商品",
                "image_url": p.image_url,
                "price": p.price,
                "currency": p.currency or "CNY",
                "sales_count": p.sales_count,
                "shop_name": "",
                "source_url": p.detail_url or p.source_url or "",
                "selection_status": p.selection_status,
                "eliminated": eliminated,
                "tier": meta.get("tier", "regular"),
                "novelty_score": meta.get("novelty"),
                "content_score": meta.get("content"),
                "highlight_reason": meta.get("reason", ""),
            }

        linked_candidates = [_didadog_item(p) for p in didadog_products if p.selection_status == "candidate"]
        linked_finals = [_didadog_item(p) for p in didadog_products if p.selection_status == "final"]
        _by_kw: dict[int, list[SelectionDidadogProduct]] = {}
        for p in didadog_products:
            _by_kw.setdefault(p.keyword_id, []).append(p)
        board_groups = [
            {
                "keyword_id": kw.id,
                "keyword": kw.keyword,
                "items": [_didadog_item(p) for p in _by_kw.get(kw.id, [])][:10],
            }
            for kw in keywords
        ]
    else:
        board_groups = [
            {
                "keyword_id": keyword.id,
                "keyword": keyword.keyword,
                "items": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "image_url": item.image_url,
                        "price": item.price,
                        "currency": item.currency,
                        "sales_count": item.sales_count,
                        "shop_name": item.shop_name,
                        "source_url": item.source_url,
                        "status": item.status,
                        "eliminated": item.status in {"not_price_seed", "eliminated", "failed"},
                    }
                    for item in candidates
                    if item.keyword_id == keyword.id
                ][:10],
            }
            for keyword in keywords
        ]
    try:
        snapshot = json.loads(task.result_snapshot or "{}")
    except ValueError:
        snapshot = {}
    return {
        "id": task.id,
        "mode": task.pipeline_mode,
        "region": snapshot.get("region") or "JP",
        "blue_ocean_strategy": snapshot.get("strategy") or "comprehensive",
        "source_product_id": task.source_product_id,
        "input_message": task.input_message,
        "status": task.status,
        "stage": task.current_stage,
        "progress": task.stage_progress,
        "message": snapshot.get("message") or task.error_message or "",
        "ai_report": snapshot.get("report_analysis") or {},
        "error_message": task.error_message,
        "counters": {
            "keywords": task.keyword_count,
            "supplier_candidates": task.supplier_candidate_count,
            "image_search_entries": task.image_search_entry_count,
            "didadog_ids": task.didadog_id_count,
            "didadog_details": task.didadog_detail_count,
            "candidates": len(linked_candidates),
            "final_products": task.final_count,
        },
        "keywords": [{"id": item.id, "keyword": item.keyword, "supplier_count": item.supplier_count, "image_search_entry_count": item.image_search_entry_count, "didadog_product_count": item.didadog_product_count} for item in keywords],
        "board_groups": board_groups,
        "candidate_items": linked_candidates,
        "final_items": linked_finals,
        "board_items": [
            {
                "id": f"1688-{item.id}",
                "source": "1688",
                "title": item.title,
                "image_url": item.image_url,
                "price": item.price,
                "currency": item.currency,
                "sales_count": item.sales_count,
                "status": item.status,
                "eliminated": item.status in {"not_price_seed", "eliminated", "failed"},
            }
            for item in candidates
        ] + [
            {
                "id": f"echotik-{item.id}",
                "source": "supply_fallback" if str(item.didadog_product_id or "").startswith("1688-") else "echotik",
                "title": item.title or item.didadog_product_id,
                "image_url": item.image_url,
                "price": item.price,
                "currency": item.currency,
                "sales_count": item.sales_count,
                "status": item.detail_status,
                "eliminated": item.detail_status in {"failed", "eliminated", "compliance_failed", "restriction_failed"},
            }
            for item in didadog_products
        ],
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


@router.post("/derivations/queue")
def queue_pending_derivations(
    payload: DerivationQueueRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    product_ids = pending_derivation_product_ids(
        db,
        limit=payload.limit,
        min_derived_count=payload.min_derived_count,
    )
    if product_ids:
        background_tasks.add_task(generate_derivatives_for_product_ids, product_ids)
    return {
        "ok": True,
        "queued_count": len(product_ids),
        "product_ids": product_ids,
        "mode": "background_one_by_one",
    }


@router.post("/suppliers/1688/queue")
def queue_pending_supplier_matches(
    payload: SupplierMatchQueueRequest,
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(
        run_supplier_match_batch,
        limit=payload.limit,
        threshold=payload.threshold,
        max_candidates=payload.max_candidates,
        page_size=payload.page_size,
    )
    return {
        "ok": True,
        "queued": True,
        "limit": payload.limit,
        "threshold": payload.threshold,
        "max_candidates": payload.max_candidates,
        "page_size": payload.page_size,
        "mode": "background_batch",
    }


@router.post("/suppliers/1688/run-now")
def run_supplier_matches_now(
    limit: int | None = Query(None, ge=1, le=100),
    threshold: float | None = Query(None, ge=0, le=100),
    max_candidates: int | None = Query(None, ge=1, le=500),
    page_size: int | None = Query(None, ge=1, le=100),
):
    return run_supplier_match_batch(
        limit=limit,
        threshold=threshold,
        max_candidates=max_candidates,
        page_size=page_size,
    )
