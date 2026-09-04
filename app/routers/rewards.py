from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user
from ..config import settings

router = APIRouter(prefix="/rewards", tags=["rewards"])

SHARE_FEATHERS_PER_STEP = 5
GITHUB_STAR_FEATHERS = 30

SHARE_FIELD_MAP = {
    "facebook": "shared_facebook",
    "instagram": "shared_instagram",
    "tiktok": "shared_tiktok",
    "x": "shared_x",
}


@router.get("/referral-link", response_model=schemas.ReferralLinkOut)
def referral_link(current_user: models.User = Depends(get_current_user)):
    return schemas.ReferralLinkOut(
        referral_code=current_user.referral_code,
        referral_link=f"{settings.FRONTEND_URL}/register?ref={current_user.referral_code}",
        referral_count=current_user.referral_count,
        feathers_earned_from_referrals=sum(
            10 * i for i in range(1, current_user.referral_count + 1)
        ),
    )


@router.post("/share", response_model=schemas.ShareClaimOut)
def claim_share(payload: schemas.ShareClaim,
                 current_user: models.User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    field = SHARE_FIELD_MAP[payload.platform]
    if getattr(current_user, field):
        raise HTTPException(status_code=400, detail="Ce partage a déjà été crédité")

    setattr(current_user, field, True)
    current_user.share_confirmed_count += 1
    awarded = SHARE_FEATHERS_PER_STEP * current_user.share_confirmed_count
    current_user.feathers_balance += awarded

    db.commit()
    db.refresh(current_user)

    return schemas.ShareClaimOut(
        platform=payload.platform,
        feathers_awarded=awarded,
        new_balance=current_user.feathers_balance,
        share_confirmed_count=current_user.share_confirmed_count,
    )


@router.post("/github-star", response_model=schemas.GithubStarClaimOut)
def claim_github_star(payload: schemas.GithubStarClaim,
                       current_user: models.User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    if current_user.github_star_claimed:
        raise HTTPException(status_code=400, detail="Étoile déjà créditée sur ce compte")

    starred = False
    try:
        with httpx.Client(timeout=8.0) as client:
            # L'API publique liste les personnes ayant mis une etoile (paginee, 100 max/page).
            # Suffisant pour un depot modeste ; au-dela il faudrait parcourir plusieurs pages.
            resp = client.get(
                f"https://api.github.com/repos/{settings.GITHUB_REPO}/stargazers",
                params={"per_page": 100},
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code == 200:
                stargazers = [u["login"].lower() for u in resp.json()]
                starred = payload.github_username.lower() in stargazers
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Impossible de vérifier sur GitHub pour le moment, réessaie plus tard")

    if not starred:
        return schemas.GithubStarClaimOut(
            starred=False,
            feathers_awarded=0,
            new_balance=current_user.feathers_balance,
            message=f"Aucune étoile trouvée depuis le compte GitHub « {payload.github_username} ». "
                    f"Mets une étoile sur {settings.GITHUB_REPO} puis réessaie.",
        )

    current_user.github_star_claimed = True
    current_user.feathers_balance += GITHUB_STAR_FEATHERS
    db.commit()
    db.refresh(current_user)

    return schemas.GithubStarClaimOut(
        starred=True,
        feathers_awarded=GITHUB_STAR_FEATHERS,
        new_balance=current_user.feathers_balance,
        message="Étoile confirmée, merci !",
    )
