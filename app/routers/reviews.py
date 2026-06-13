from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.db_depends import get_async_db


from app.models.review import Review as ReviewModel
from app.schemas import Review as ReviewSchema, ReviewCreate
from app.models.users import User as UserModel
from app.auth import get_current_buyer, get_current_user
from app.models.products import Product as ProductModel
from sqlalchemy.sql import func


router = APIRouter(prefix='/reviews', tags=['reviews'])


async def update_product_rating(db: AsyncSession, product_id: int):
    result = await db.execute(
        select(func.avg(ReviewModel.grade)).where(
            ReviewModel.product_id == product_id,
            ReviewModel.is_active == True
        )
    )
    avg_rating = result.scalar() or 0.0
    product = await db.get(ProductModel, product_id)
    product.rating = avg_rating
    await db.commit()



@router.get('/', response_model=list[ReviewSchema])
async def get_all_reviews(db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список всех активных отзывов о товарах
    """
    result = await db.scalars(select(ReviewModel).where(ReviewModel.is_active == True))
    reviews = result.all()
    return reviews


@router.get('/products/{product_id}', response_model=list[ReviewSchema])
async def get_review(product_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список активных отзывов для указанного товара
    """
    product = await db.scalar(select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True))
    product = product.first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден или неактивен")
    
    result = await db.scalars(select(ReviewModel).where(ReviewModel.product_id == product_id, ReviewModel.is_active == True))
    review_product = result.all()
    
    return review_product


@router.post('/', response_model=ReviewSchema, status_code=status.HTTP_201_CREATED)
async def create_review(review: ReviewCreate, db: AsyncSession = Depends(get_async_db), current_user: UserModel = Depends(get_current_buyer)):


    product = await db.scalars(select(ProductModel).where(ProductModel.id == review.product_id, ProductModel.is_active == True))
    if not product.first():
        raise HTTPException(status=404, detail='Товар не найден')
    
    db_review = ReviewModel(**review.model_dump(), user_id=current_user.id)
    db.add(db_review)
    await update_product_rating(db, review.product_id)
    await db.refresh(db_review)

    return db_review



@router.delete("/{review_id}")
async def delete_review(review_id: int, db: AsyncSession = Depends(get_async_db),
                        current_user: UserModel = Depends(get_current_user)):
    
    review = await db.scalars(select(ReviewModel.id == review_id, ReviewModel.is_active == True))
    review = review.first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отзыв не найден или неактивен")
    

    if review.user_id != current_user.id or current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Отзыв может удалять Автор отзыва или пользователи с ролью Admin")
    
    await db.execute(
        update(ReviewModel)
        .where(ReviewModel.id == review_id)
        .values(is_active=False)
    )
    product_id = review.product_id
    
    await db.commit()
    await update_product_rating(db, product_id)
    return {"message": "Review deleted"}

