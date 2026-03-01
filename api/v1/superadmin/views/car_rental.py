"""
SuperAdmin Car Rental API: companies and cars (CRUD, gallery, create-from-json).
"""

import logging
import re
import uuid
from decimal import Decimal

from django.utils import timezone
from django.utils.text import slugify
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.car_rental.models import Car, CarRentalCompany
from apps.media.models import MediaAsset
from apps.organizers.models import Organizer

from ..permissions import IsSuperUser
from ..serializers import JsonCarRentalCompanyCreateSerializer, JsonCarCreateSerializer

logger = logging.getLogger(__name__)


def _build_car_gallery_with_urls(car, request=None):
    """Return list of {media_id, sort_order, is_principal, image_url} for car gallery."""
    from django.conf import settings as django_settings
    items = []
    for i, mid in enumerate(car.gallery_media_ids or []):
        items.append({"media_id": str(mid), "sort_order": i, "is_principal": i == 0})
    if not items:
        return []
    ids = [str(it["media_id"]) for it in items]
    assets = MediaAsset.objects.filter(id__in=ids, deleted_at__isnull=True)
    asset_map = {str(a.id): a for a in assets if a.file}
    base = getattr(django_settings, "BACKEND_URL", "").rstrip("/")
    result = []
    for it in items:
        asset = asset_map.get(it["media_id"])
        url = ""
        if asset and asset.file:
            raw = asset.file.url
            if raw.startswith(("http://", "https://")):
                url = raw
            elif request:
                url = request.build_absolute_uri(raw)
            else:
                path = raw if raw.startswith("/") else f"/{raw.lstrip('/')}"
                url = f"{base}{path}" if base else raw
        result.append({
            "media_id": it["media_id"],
            "sort_order": it["sort_order"],
            "is_principal": it.get("is_principal", False),
            "image_url": url,
        })
    return result


# ---------- Companies ----------


class SuperAdminCarRentalCompanyListView(APIView):
    """GET /api/v1/superadmin/car-rental/companies/  POST (create)."""

    permission_classes = [IsSuperUser]

    def get(self, request):
        qs = CarRentalCompany.objects.all().order_by("name")
        organizer_id = request.query_params.get("organizer_id", "").strip()
        if organizer_id:
            qs = qs.filter(organizer_id=organizer_id)
        data = [
            {
                "id": str(c.id),
                "name": c.name,
                "slug": c.slug,
                "is_active": c.is_active,
                "cars_count": c.cars.filter(deleted_at__isnull=True).count(),
            }
            for c in qs
        ]
        return Response(data)

    def post(self, request):
        data = request.data or {}
        serializer = JsonCarRentalCompanyCreateSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        v = serializer.validated_data
        organizer_id = v.pop("organizer_id", None)
        organizer = None
        if organizer_id:
            try:
                organizer = Organizer.objects.get(id=organizer_id)
            except Organizer.DoesNotExist:
                return Response({"detail": "Organizador no encontrado."}, status=status.HTTP_400_BAD_REQUEST)
        name = (v.get("name") or "").strip()
        if not name:
            return Response({"detail": "name es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        slug = slugify(v.get("slug") or name) or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "rent-a-car"
        if CarRentalCompany.objects.filter(slug=slug).exists():
            return Response({"detail": f"Ya existe una empresa con slug '{slug}'."}, status=status.HTTP_400_BAD_REQUEST)
        company = CarRentalCompany(
            name=name,
            slug=slug,
            organizer=organizer,
            short_description=(v.get("short_description") or "")[:500],
            description=(v.get("description") or ""),
            hero_media_id=v.get("hero_media_id"),
            gallery_media_ids=[str(u) for u in (v.get("gallery_media_ids") or [])][:50],
            conditions=v.get("conditions") or {},
            is_active=v.get("is_active", True),
            country=(v.get("country") or "")[:255],
            city=(v.get("city") or "")[:255],
        )
        company.save()
        return Response({
            "id": str(company.id),
            "name": company.name,
            "slug": company.slug,
        }, status=status.HTTP_201_CREATED)


class SuperAdminCarRentalCompanyDetailView(APIView):
    """GET /api/v1/superadmin/car-rental/companies/<uuid>/  PATCH  DELETE."""

    permission_classes = [IsSuperUser]

    def _get(self, pk):
        return CarRentalCompany.objects.get(id=pk)

    def get(self, request, pk):
        try:
            company = self._get(pk)
        except (CarRentalCompany.DoesNotExist, ValueError):
            return Response({"detail": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "id": str(company.id),
            "name": company.name,
            "slug": company.slug,
            "short_description": company.short_description or "",
            "description": company.description or "",
            "hero_media_id": str(company.hero_media_id) if company.hero_media_id else None,
            "gallery_media_ids": company.gallery_media_ids or [],
            "conditions": company.conditions or {},
            "is_active": company.is_active,
            "organizer_id": str(company.organizer_id) if company.organizer_id else None,
            "country": company.country or "",
            "city": company.city or "",
        })

    def patch(self, request, pk):
        try:
            company = self._get(pk)
        except (CarRentalCompany.DoesNotExist, ValueError):
            return Response({"detail": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data or {}
        for field in ("name", "country", "city"):
            if field in data:
                setattr(company, field, (str(data[field]) if data[field] is not None else "")[:255])
        for field in ("short_description", "description"):
            if field in data:
                val = str(data[field]) if data[field] is not None else ""
                setattr(company, field, val[:500] if field == "short_description" else val)
        if "slug" in data and data["slug"]:
            company.slug = slugify(str(data["slug"]))[:255]
        if "is_active" in data:
            company.is_active = bool(data["is_active"])
        if "conditions" in data and isinstance(data["conditions"], dict):
            company.conditions = data["conditions"]
        if "gallery_media_ids" in data and isinstance(data["gallery_media_ids"], list):
            company.gallery_media_ids = [str(u) for u in data["gallery_media_ids"]][:50]
        if "hero_media_id" in data:
            company.hero_media_id = data["hero_media_id"]
        if "organizer_id" in data:
            if data["organizer_id"] is None:
                company.organizer_id = None
            else:
                try:
                    company.organizer = Organizer.objects.get(id=data["organizer_id"])
                except Organizer.DoesNotExist:
                    pass
        company.save()
        return self.get(request, pk)

    def delete(self, request, pk):
        try:
            company = self._get(pk)
        except (CarRentalCompany.DoesNotExist, ValueError):
            return Response({"detail": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        company.cars.update(deleted_at=timezone.now())
        company.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------- Cars ----------


class SuperAdminCarListView(APIView):
    """GET /api/v1/superadmin/car-rental/cars/  POST (create). Query: company_id."""

    permission_classes = [IsSuperUser]

    def get(self, request):
        qs = Car.objects.filter(deleted_at__isnull=True).select_related("company").order_by("company__name", "title")
        company_id = request.query_params.get("company_id", "").strip()
        if company_id:
            qs = qs.filter(company_id=company_id)
        data = []
        for c in qs:
            imgs = c.gallery_media_ids or c.images
            image_url = ""
            if imgs and isinstance(imgs, list) and len(imgs) > 0:
                first_id = imgs[0]
                if isinstance(first_id, str) and len(first_id) == 36:
                    a = MediaAsset.objects.filter(id=first_id, deleted_at__isnull=True).first()
                    if a and a.file:
                        image_url = a.file.url
                elif isinstance(imgs[0], str) and imgs[0].startswith("http"):
                    image_url = imgs[0]
            data.append({
                "id": str(c.id),
                "title": c.title,
                "slug": c.slug,
                "company_id": str(c.company_id),
                "company_name": c.company.name if c.company else "",
                "status": c.status,
                "price_per_day": float(c.price_per_day or 0),
                "currency": c.currency or "CLP",
                "image_url": image_url,
            })
        return Response(data)

    def post(self, request):
        data = request.data or {}
        serializer = JsonCarCreateSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        v = serializer.validated_data
        try:
            company = CarRentalCompany.objects.get(id=v["company_id"])
        except CarRentalCompany.DoesNotExist:
            return Response({"detail": "Empresa no encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        title = (v.get("title") or "").strip()
        if not title:
            return Response({"detail": "title es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        slug = slugify(v.get("slug") or title) or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "auto"
        if Car.objects.filter(slug=slug, deleted_at__isnull=True).exists():
            return Response({"detail": f"Ya existe un auto con slug '{slug}'."}, status=status.HTTP_400_BAD_REQUEST)
        car = Car(
            company=company,
            title=title,
            slug=slug,
            description=(v.get("description") or ""),
            short_description=(v.get("short_description") or "")[:500],
            status=v.get("status", "draft"),
            price_per_day=Decimal(str(v.get("price_per_day", 0))),
            currency=(v.get("currency") or "CLP")[:3],
            pickup_time_default=(v.get("pickup_time_default") or "")[:5],
            return_time_default=(v.get("return_time_default") or "")[:5],
            included=[str(x) for x in (v.get("included") or [])],
            not_included=[str(x) for x in (v.get("not_included") or [])],
            inherit_company_conditions=v.get("inherit_company_conditions", True),
            conditions_override=v.get("conditions_override") or {},
            gallery_media_ids=[str(u) for u in (v.get("gallery_media_ids") or [])][:50],
            images=[str(x) for x in (v.get("images") or [])][:50],
            min_driver_age=v.get("min_driver_age"),
            transmission=(v.get("transmission") or "manual")[:20],
            seats=v.get("seats"),
            bags=v.get("bags"),
        )
        car.save()
        return Response({
            "id": str(car.id),
            "title": car.title,
            "slug": car.slug,
            "company_id": str(car.company_id),
        }, status=status.HTTP_201_CREATED)


class SuperAdminCarDetailView(APIView):
    """GET PATCH DELETE /api/v1/superadmin/car-rental/cars/<uuid>/."""

    permission_classes = [IsSuperUser]

    def _get(self, pk):
        return Car.objects.get(id=pk, deleted_at__isnull=True)

    def get(self, request, pk):
        try:
            car = self._get(pk)
        except (Car.DoesNotExist, ValueError):
            return Response({"detail": "Auto no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        gallery = _build_car_gallery_with_urls(car, request)
        return Response({
            "id": str(car.id),
            "title": car.title,
            "slug": car.slug,
            "company_id": str(car.company_id),
            "company_name": car.company.name if car.company else "",
            "description": car.description or "",
            "short_description": car.short_description or "",
            "status": car.status,
            "price_per_day": float(car.price_per_day or 0),
            "currency": car.currency or "CLP",
            "pickup_time_default": car.pickup_time_default or "",
            "return_time_default": car.return_time_default or "",
            "included": car.included or [],
            "not_included": car.not_included or [],
            "inherit_company_conditions": car.inherit_company_conditions,
            "conditions_override": car.conditions_override or {},
            "gallery_media_ids": car.gallery_media_ids or [],
            "gallery_items": gallery,
            "photo_count": len(gallery),
            "min_driver_age": car.min_driver_age,
            "transmission": car.transmission or "manual",
            "seats": car.seats,
            "bags": car.bags,
        })

    def patch(self, request, pk):
        try:
            car = self._get(pk)
        except (Car.DoesNotExist, ValueError):
            return Response({"detail": "Auto no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data or {}
        if "title" in data:
            car.title = (str(data["title"]) or "")[:255]
        if "description" in data:
            car.description = str(data["description"]) if data["description"] is not None else ""
        if "short_description" in data:
            car.short_description = (str(data["short_description"]) or "")[:500]
        if "pickup_time_default" in data:
            car.pickup_time_default = (str(data["pickup_time_default"]) or "")[:5]
        if "return_time_default" in data:
            car.return_time_default = (str(data["return_time_default"]) or "")[:5]
        if "currency" in data and data["currency"]:
            car.currency = str(data["currency"])[:3]
        if "slug" in data and data["slug"]:
            car.slug = slugify(str(data["slug"]))[:255]
        if "status" in data and data["status"] in ("draft", "published", "cancelled"):
            car.status = data["status"]
        if "price_per_day" in data:
            try:
                car.price_per_day = Decimal(str(data["price_per_day"]))
                if car.price_per_day < 0:
                    car.price_per_day = Decimal("0")
            except (TypeError, ValueError):
                pass
        if "included" in data and isinstance(data["included"], list):
            car.included = [str(x) for x in data["included"]]
        if "not_included" in data and isinstance(data["not_included"], list):
            car.not_included = [str(x) for x in data["not_included"]]
        if "inherit_company_conditions" in data:
            car.inherit_company_conditions = bool(data["inherit_company_conditions"])
        if "conditions_override" in data and isinstance(data["conditions_override"], dict):
            car.conditions_override = data["conditions_override"]
        if "gallery_media_ids" in data and isinstance(data["gallery_media_ids"], list):
            car.gallery_media_ids = [str(u) for u in data["gallery_media_ids"]][:50]
        if "min_driver_age" in data:
            car.min_driver_age = data["min_driver_age"]
        if "transmission" in data and data["transmission"] in ("manual", "automatic"):
            car.transmission = data["transmission"]
        if "seats" in data:
            car.seats = data["seats"]
        if "bags" in data:
            car.bags = data["bags"]
        if "company_id" in data:
            try:
                car.company = CarRentalCompany.objects.get(id=data["company_id"])
            except CarRentalCompany.DoesNotExist:
                pass
        car.save()
        return self.get(request, pk)

    def delete(self, request, pk):
        try:
            car = self._get(pk)
        except (Car.DoesNotExist, ValueError):
            return Response({"detail": "Auto no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        car.deleted_at = timezone.now()
        car.save(update_fields=["deleted_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SuperAdminCarGalleryUpdateView(APIView):
    """PATCH /api/v1/superadmin/car-rental/cars/<uuid>/gallery/  Body: { gallery_media_ids: [uuid, ...] }."""

    permission_classes = [IsSuperUser]

    def patch(self, request, pk):
        try:
            car = Car.objects.get(id=pk, deleted_at__isnull=True)
        except (Car.DoesNotExist, ValueError):
            return Response({"detail": "Auto no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data or {}
        ids = data.get("gallery_media_ids")
        if ids is None:
            return Response({"detail": "gallery_media_ids es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(ids, list):
            return Response({"detail": "gallery_media_ids debe ser una lista."}, status=status.HTTP_400_BAD_REQUEST)
        normalized = []
        for i, mid in enumerate(ids[:50]):
            try:
                normalized.append(str(uuid.UUID(str(mid))))
            except (ValueError, TypeError):
                continue
        if normalized:
            found = MediaAsset.objects.filter(id__in=normalized, deleted_at__isnull=True).count()
            if found != len(normalized):
                return Response({"detail": "Algunos media_id no existen."}, status=status.HTTP_400_BAD_REQUEST)
        car.gallery_media_ids = normalized
        car.images = []
        car.save(update_fields=["gallery_media_ids", "images"])
        gallery = _build_car_gallery_with_urls(car, request)
        return Response({"gallery_items": gallery, "photo_count": len(gallery)})


# ---------- Create from JSON ----------


@api_view(["POST"])
@permission_classes([IsSuperUser])
def create_car_rental_company_from_json(request):
    """POST /api/v1/superadmin/car-rental/companies/create-from-json/  Body: { company_data: {...}, cars: [...] optional }."""
    data = request.data or {}
    company_data = data.get("company_data")
    if not company_data:
        return Response({"detail": "company_data es requerido."}, status=status.HTTP_400_BAD_REQUEST)
    serializer = JsonCarRentalCompanyCreateSerializer(data=company_data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    v = serializer.validated_data
    organizer_id = v.pop("organizer_id", None)
    organizer = None
    if organizer_id:
        try:
            organizer = Organizer.objects.get(id=organizer_id)
        except Organizer.DoesNotExist:
            return Response({"detail": "Organizador no encontrado."}, status=status.HTTP_400_BAD_REQUEST)
    name = (v.get("name") or "").strip()
    if not name:
        return Response({"detail": "name es requerido."}, status=status.HTTP_400_BAD_REQUEST)
    slug = slugify(v.get("slug") or name) or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "rent-a-car"
    if CarRentalCompany.objects.filter(slug=slug).exists():
        return Response({"detail": f"Ya existe una empresa con slug '{slug}'."}, status=status.HTTP_400_BAD_REQUEST)
    company = CarRentalCompany(
        name=name, slug=slug, organizer=organizer,
        short_description=(v.get("short_description") or "")[:500],
        description=(v.get("description") or ""),
        hero_media_id=v.get("hero_media_id"),
        gallery_media_ids=[str(u) for u in (v.get("gallery_media_ids") or [])][:50],
        conditions=v.get("conditions") or {},
        is_active=v.get("is_active", True),
        country=(v.get("country") or "")[:255],
        city=(v.get("city") or "")[:255],
    )
    company.save()
    created_cars = []
    for item in (data.get("cars") or []):
        item = dict(item)
        item["company_id"] = str(company.id)
        ser = JsonCarCreateSerializer(data=item)
        if not ser.is_valid():
            continue
        vc = ser.validated_data
        title = (vc.get("title") or "").strip()
        if not title:
            continue
        car_slug = slugify(vc.get("slug") or title) or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "auto"
        if Car.objects.filter(slug=car_slug, deleted_at__isnull=True).exists():
            car_slug = f"{car_slug}-{str(company.id)[:8]}"
        car = Car(
            company=company, title=title, slug=car_slug,
            description=(vc.get("description") or ""),
            short_description=(vc.get("short_description") or "")[:500],
            status=vc.get("status", "draft"),
            price_per_day=Decimal(str(vc.get("price_per_day", 0))),
            currency=(vc.get("currency") or "CLP")[:3],
            pickup_time_default=(vc.get("pickup_time_default") or "")[:5],
            return_time_default=(vc.get("return_time_default") or "")[:5],
            included=[str(x) for x in (vc.get("included") or [])],
            not_included=[str(x) for x in (vc.get("not_included") or [])],
            inherit_company_conditions=vc.get("inherit_company_conditions", True),
            conditions_override=vc.get("conditions_override") or {},
            gallery_media_ids=[str(u) for u in (vc.get("gallery_media_ids") or [])][:50],
            images=[str(x) for x in (vc.get("images") or [])][:50],
            min_driver_age=vc.get("min_driver_age"),
            transmission=(vc.get("transmission") or "manual")[:20],
            seats=vc.get("seats"),
            bags=vc.get("bags"),
        )
        car.save()
        created_cars.append({"id": str(car.id), "title": car.title, "slug": car.slug})
    return Response({
        "company": {"id": str(company.id), "name": company.name, "slug": company.slug},
        "cars": created_cars,
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsSuperUser])
def create_car_from_json(request):
    """POST /api/v1/superadmin/car-rental/cars/create-from-json/  Body: { car_data: {...} } or { cars: [...], company_id: uuid }."""
    data = request.data or {}
    if "cars" in data and "company_id" in data:
        company_id = data["company_id"]
        try:
            company = CarRentalCompany.objects.get(id=company_id)
        except CarRentalCompany.DoesNotExist:
            return Response({"detail": "Empresa no encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        created = []
        for item in data["cars"]:
            item = dict(item)
            item["company_id"] = str(company_id)
            ser = JsonCarCreateSerializer(data=item)
            if not ser.is_valid():
                continue
            v = ser.validated_data
            title = (v.get("title") or "").strip()
            if not title:
                continue
            slug = slugify(v.get("slug") or title) or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "auto"
            if Car.objects.filter(slug=slug, deleted_at__isnull=True).exists():
                slug = f"{slug}-{str(company_id)[:8]}"
            car = Car(
                company=company, title=title, slug=slug,
                description=(v.get("description") or ""),
                short_description=(v.get("short_description") or "")[:500],
                status=v.get("status", "draft"),
                price_per_day=Decimal(str(v.get("price_per_day", 0))),
                currency=(v.get("currency") or "CLP")[:3],
                pickup_time_default=(v.get("pickup_time_default") or "")[:5],
                return_time_default=(v.get("return_time_default") or "")[:5],
                included=[str(x) for x in (v.get("included") or [])],
                not_included=[str(x) for x in (v.get("not_included") or [])],
                inherit_company_conditions=v.get("inherit_company_conditions", True),
                conditions_override=v.get("conditions_override") or {},
                gallery_media_ids=[str(u) for u in (v.get("gallery_media_ids") or [])][:50],
                images=[str(x) for x in (v.get("images") or [])][:50],
                min_driver_age=v.get("min_driver_age"),
                transmission=(v.get("transmission") or "manual")[:20],
                seats=v.get("seats"),
                bags=v.get("bags"),
            )
            car.save()
            created.append({"id": str(car.id), "title": car.title, "slug": car.slug})
        return Response({"cars": created}, status=status.HTTP_201_CREATED)

    car_data = data.get("car_data")
    if not car_data:
        return Response({"detail": "car_data o (cars + company_id) es requerido."}, status=status.HTTP_400_BAD_REQUEST)
    car_data = dict(car_data)
    if "company_id" not in car_data:
        return Response({"detail": "company_id es requerido en car_data."}, status=status.HTTP_400_BAD_REQUEST)
    serializer = JsonCarCreateSerializer(data=car_data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    v = serializer.validated_data
    try:
        company = CarRentalCompany.objects.get(id=v["company_id"])
    except CarRentalCompany.DoesNotExist:
        return Response({"detail": "Empresa no encontrada."}, status=status.HTTP_400_BAD_REQUEST)
    title = (v.get("title") or "").strip()
    if not title:
        return Response({"detail": "title es requerido."}, status=status.HTTP_400_BAD_REQUEST)
    slug = slugify(v.get("slug") or title) or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "auto"
    if Car.objects.filter(slug=slug, deleted_at__isnull=True).exists():
        return Response({"detail": f"Ya existe un auto con slug '{slug}'."}, status=status.HTTP_400_BAD_REQUEST)
    car = Car(
        company=company, title=title, slug=slug,
        description=(v.get("description") or ""),
        short_description=(v.get("short_description") or "")[:500],
        status=v.get("status", "draft"),
        price_per_day=Decimal(str(v.get("price_per_day", 0))),
        currency=(v.get("currency") or "CLP")[:3],
        pickup_time_default=(v.get("pickup_time_default") or "")[:5],
        return_time_default=(v.get("return_time_default") or "")[:5],
        included=[str(x) for x in (v.get("included") or [])],
        not_included=[str(x) for x in (v.get("not_included") or [])],
        inherit_company_conditions=v.get("inherit_company_conditions", True),
        conditions_override=v.get("conditions_override") or {},
        gallery_media_ids=[str(u) for u in (v.get("gallery_media_ids") or [])][:50],
        images=[str(x) for x in (v.get("images") or [])][:50],
        min_driver_age=v.get("min_driver_age"),
        transmission=(v.get("transmission") or "manual")[:20],
        seats=v.get("seats"),
        bags=v.get("bags"),
    )
    car.save()
    return Response({"id": str(car.id), "title": car.title, "slug": car.slug}, status=status.HTTP_201_CREATED)
