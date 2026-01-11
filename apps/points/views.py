from rest_framework import permissions
from apps.routes.models import Point, ReviewPoint, FavoritePoint
from rest_framework.response import Response
from django.db import models
from rest_framework.views import APIView
from django.utils import timezone
# Create your views here.
def update_point_rating(point: Point):
    reviews = point.reviews.all()
    if not reviews.exists():
        point.average_rating = 0
        point.reviews_count = 0
        point.save(update_fields=["average_rating", "reviews_count"])
        return

    avg = reviews.aggregate(models.Avg("rating"))["rating__avg"]
    count = reviews.count()

    point.average_rating = round(avg, 1)
    point.reviews_count = count
    point.save(update_fields=["average_rating", "reviews_count"])


class ReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, point_id):
        rating = request.data.get("rating")
        comment = request.data.get("comment", "")
        if not rating:
            return Response({"error": "rating is required"}, status=400)
        try:
            rating = float(rating)
            if rating < 1 or rating > 5:
                raise ValueError
        except:
            return Response({"error": "rating must be between 1 and 5"}, status=400)

        try:
            point = Point.objects.get(id=point_id)
        except Point.DoesNotExist:
            return Response({"error": "Point not found"}, status=404)

        review, created = ReviewPoint.objects.update_or_create(
            user=request.user,
            point=point,
            defaults={"rating": rating, "comment": comment}
        )

        update_point_rating(point)

        return Response({
            "status": "success",
            "created": created,
        })


class PointDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, point_id):
        try:
            point = Point.objects.get(id=point_id)
        except Point.DoesNotExist:
            return Response({"status": "error", "message": "Point not found"}, status=404)

        # Последние 5 отзывов
        last_reviews = (
            ReviewPoint.objects
            .filter(point=point)
            .order_by("-created_at")[:5]
        )

        reviews_payload = [
            {
                "user_id": r.user.id,
                "username": r.user.username,
                "rating": float(r.rating),
                "comment": r.comment,
                "created_at": r.created_at.isoformat()
            }
            for r in last_reviews
        ]

        data = {
            "id": point.id,
            "name": point.name,
            "description": point.description,
            "image_url": point.image_url,
            "address": point.address,
            "city": point.city.name,
            "area": point.area.name if point.area else None,
            "coordinates": {
                "lat": float(point.coordinates_lat),
                "lng": float(point.coordinates_lng),
            },
            "average_visit_duration": point.average_visit_duration,
            "average_cost": point.average_cost,
            "average_rating": float(point.average_rating),
            "reviews_count": point.reviews_count,
            "tags": [t.name for t in point.tags.all()],
            "interests": [{"id": i.id, "label": i.label} for i in point.interests.all()],
            "moods": [{"id": m.id, "label": m.label} for m in point.moods.all()],
            "best_visit_time": point.best_visit_time,
            "working_hours": point.working_hours_json,
            "seasonality": {
                "is_seasonal": point.is_seasonal,
                "months": point.seasonal_months or []
            },
            "analytics": {
                "view_count": point.view_count,
                "success_rate": float(point.success_rate),
                "last_viewed_at": point.last_viewed_at.isoformat() if point.last_viewed_at else None,
            },
            "last_reviews": reviews_payload
        }

        return Response({"status": "success", "data": data}, status=200)


class PointAllReviewsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, point_id):
        try:
            point = Point.objects.get(id=point_id)
        except Point.DoesNotExist:
            return Response({"status": "error", "message": "Point not found"}, status=404)

        page = int(request.GET.get("page", 1))
        page_size = 20
        offset = (page - 1) * page_size

        qs = (
            ReviewPoint.objects
            .filter(point=point)
            .select_related("user")
            .order_by("-created_at")
        )

        total = qs.count()
        reviews = qs[offset:offset + page_size]

        reviews_payload = [
            {
                "user_id": r.user.id,
                "username": r.user.username,
                "rating": float(r.rating),
                "comment": r.comment,
                "created_at": r.created_at.isoformat()
            }
            for r in reviews
        ]

        return Response({
            "status": "success",
            "data": {
                "point_id": point.id,
                "average_rating": float(point.average_rating),
                "reviews_count": point.reviews_count,
                "page": page,
                "page_size": page_size,
                "total": total,
                "reviews": reviews_payload
            }
        }, status=200)


class ToggleFavoritePointView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, point_id):
        try:
            point = Point.objects.get(id=point_id)
        except Point.DoesNotExist:
            return Response({"error": "Point not found"}, status=404)

        fav, created = FavoritePoint.objects.get_or_create(
            user=request.user,
            point=point
        )

        if not created:
            fav.delete()
            return Response({"status": "removed"})

        return Response({"status": "added"})


class UpdateFavoriteNoteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, point_id):
        note = request.data.get("note", "")

        try:
            point = Point.objects.get(id=point_id)
        except Point.DoesNotExist:
            return Response({"error": "Point not found"}, status=404)

        fav, _ = FavoritePoint.objects.get_or_create(
            user=request.user,
            point=point
        )

        fav.note = note
        fav.save(update_fields=["note"])

        return Response({"status": "success", "note": fav.note})

class UserFavoritePointsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        favorites = (
            FavoritePoint.objects
            .filter(user=request.user)
            .select_related("point")
            .order_by("-created_at")
        )

        data = [
            {
                "id": fav.point.id,
                "name": fav.point.name,
                "image_url": fav.point.image_url,
                "description":fav.point.description,
                "average_rating": float(fav.point.average_rating),
                "coordinates": {
                    "lat": float(fav.point.coordinates_lat),
                    "lng": float(fav.point.coordinates_lng),
                },
                "note": fav.note,  # ← заметка
                "added_at": fav.created_at.isoformat()
            }
            for fav in favorites
        ]

        return Response({"status": "success", "data": data})
