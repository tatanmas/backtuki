"""Serializers for travel guides: public (list/detail with expanded embeds) and superadmin CRUD."""

from rest_framework import serializers
from .models import TravelGuide
from .booking import build_public_booking_offer, ensure_embed_block_keys


def _resolve_hero_url(guide, request=None):
    """Resolve hero image URL from hero_media_id or hero_image fallback."""
    if guide.hero_media_id:
        from apps.media.models import MediaAsset
        asset = MediaAsset.objects.filter(
            id=guide.hero_media_id, deleted_at__isnull=True
        ).first()
        if asset and getattr(asset, 'file', None) and asset.file:
            if request:
                return request.build_absolute_uri(asset.file.url)
            return asset.file.url if hasattr(asset.file, 'url') else getattr(asset, 'url', '') or ''
        if getattr(asset, 'url', None):
            return asset.url
    if guide.hero_image:
        return guide.hero_image
    return ''


def _asset_url(media_id, request=None):
    """Resolve a single media asset to absolute URL."""
    if not media_id:
        return ''
    from apps.media.models import MediaAsset
    a = MediaAsset.objects.filter(id=media_id, deleted_at__isnull=True).first()
    if not a:
        return ''
    if getattr(a, 'file', None) and a.file:
        return request.build_absolute_uri(a.file.url) if request else (getattr(a.file, 'url', '') or '')
    return getattr(a, 'url', '') or ''


def _resolve_hero_slides(guide, request=None):
    """Resolve hero_slides to list of { image, caption } for public API."""
    slides = getattr(guide, 'hero_slides', None) or []
    if not isinstance(slides, list):
        return []
    result = []
    for s in slides:
        if not isinstance(s, dict):
            continue
        media_id = s.get('media_id')
        if not media_id:
            continue
        url = _asset_url(media_id, request)
        if not url:
            continue
        result.append({
            'image': url,
            'caption': (s.get('caption') or '').strip()[:500],
        })
    return result


def _expand_embed_blocks(body, request=None, guide=None):
    """
    In-place expand embed_* blocks with resolved entity data for public API.
    Also resolves gallery blocks (media_ids -> images) and image blocks with media_asset_id.
    """
    if not body or not isinstance(body, list):
        return body
    from apps.media.models import MediaAsset

    def _asset_url(media_id):
        if not media_id:
            return ''
        a = MediaAsset.objects.filter(id=media_id, deleted_at__isnull=True).first()
        if not a:
            return ''
        if getattr(a, 'file', None) and a.file:
            return request.build_absolute_uri(a.file.url) if request else (getattr(a.file, 'url', '') or '')
        return getattr(a, 'url', '') or ''

    def _experience_image(exp):
        imgs = getattr(exp, 'images', None) or []
        if not imgs:
            return ''
        first = imgs[0] if imgs else None
        if isinstance(first, str):
            url = first
        elif isinstance(first, dict):
            url = (first.get('url') or first.get('image') or first.get('src')) or ''
        else:
            return ''
        if request and url and url.startswith('/'):
            return request.build_absolute_uri(url)
        return url or ''

    expanded_body = []
    for block in ensure_embed_block_keys(body or []):
        if not isinstance(block, dict):
            expanded_body.append(block)
            continue
        b = dict(block)
        btype = b.get('type')
        if btype == 'embed_experience':
            eid = b.get('experience_id')
            if eid:
                from apps.experiences.models import Experience
                exp = Experience.objects.filter(id=eid, status='published').first()
                if exp:
                    b['expanded'] = {
                        'id': str(exp.id),
                        'title': exp.title,
                        'slug': getattr(exp, 'slug', ''),
                        'image': _experience_image(exp),
                        'duration': f'{exp.duration_minutes} min' if getattr(exp, 'duration_minutes', None) else None,
                        'price': float(exp.price) if getattr(exp, 'price', None) is not None else None,
                    }
            if guide:
                b['booking_offer'] = build_public_booking_offer(guide, b)
            expanded_body.append(b)
        elif btype == 'embed_experiences':
            eids = b.get('experience_ids') or []
            from apps.experiences.models import Experience
            exps = Experience.objects.filter(id__in=eids, status='published').order_by('title')
            b['expanded'] = [
                {
                    'id': str(e.id),
                    'title': e.title,
                    'slug': getattr(e, 'slug', ''),
                    'image': _experience_image(e),
                    'duration': f'{e.duration_minutes} min' if getattr(e, 'duration_minutes', None) else None,
                    'price': float(e.price) if getattr(e, 'price', None) is not None else None,
                }
                for e in exps
            ]
            expanded_body.append(b)
        elif btype == 'embed_accommodation':
            aid = b.get('accommodation_id')
            if aid:
                from apps.accommodations.models import Accommodation
                from apps.accommodations.helpers import build_gallery_items_with_urls
                acc = Accommodation.objects.filter(id=aid, status='published').first()
                if acc:
                    img = ''
                    items_with_urls = build_gallery_items_with_urls(acc, request)
                    if items_with_urls:
                        principal_item = next(
                            (it for it in items_with_urls if it.get('is_principal')),
                            items_with_urls[0],
                        )
                        img = (principal_item.get('image_url') or '').strip()
                    if not img:
                        gallery_ids = getattr(acc, 'gallery_media_ids', None) or []
                        if gallery_ids:
                            img = _asset_url(gallery_ids[0])
                    if not img and (getattr(acc, 'images', None) or []):
                        first_img = acc.images[0]
                        img = first_img if isinstance(first_img, str) else (first_img.get('url') or first_img.get('image') or '')
                    b['expanded'] = {
                        'id': str(acc.id),
                        'title': acc.title,
                        'slug': getattr(acc, 'slug', ''),
                        'image': img or '',
                        'price': float(acc.price) if getattr(acc, 'price', None) is not None else None,
                        'guests': getattr(acc, 'guests', None),
                        'bedrooms': getattr(acc, 'bedrooms', None),
                        'bathrooms': getattr(acc, 'bathrooms', None),
                        'beds': getattr(acc, 'beds', None),
                    }
            expanded_body.append(b)
        elif btype == 'embed_event':
            eid = b.get('event_id')
            if eid:
                from apps.events.models import Event
                ev = Event.objects.filter(id=eid, status='published').first()
                if ev:
                    img = ''
                    if hasattr(ev, 'images') and ev.images.exists():
                        first_img = ev.images.first()
                        if first_img and getattr(first_img, 'image', None):
                            url = getattr(first_img.image, 'url', None) or ''
                            if url and request:
                                img = request.build_absolute_uri(url)
                            else:
                                img = url or ''
                    b['expanded'] = {
                        'id': str(ev.id),
                        'title': ev.title,
                        'slug': getattr(ev, 'slug', ''),
                        'image': img,
                        'start_date': ev.start_date.isoformat() if getattr(ev, 'start_date', None) else None,
                    }
            expanded_body.append(b)
        elif btype == 'embed_destination':
            slug = b.get('destination_slug')
            if slug:
                from apps.landing_destinations.models import LandingDestination
                dest = LandingDestination.objects.filter(slug=slug, is_active=True).first()
                if dest:
                    hero = ''
                    if dest.hero_media_id:
                        hero = _asset_url(dest.hero_media_id)
                    if not hero and dest.hero_image:
                        hero = dest.hero_image
                    b['expanded'] = {
                        'slug': dest.slug,
                        'name': dest.name,
                        'image': hero,
                    }
            expanded_body.append(b)
        elif btype == 'embed_erasmus_activity':
            aid = b.get('erasmus_activity_id')
            if aid:
                from apps.erasmus.models import ErasmusActivity
                from apps.erasmus.activity_display import get_activity_display_data
                act = ErasmusActivity.objects.filter(id=aid, is_active=True).select_related('experience').first()
                if act:
                    display = get_activity_display_data(act)
                    img = (display.get('image') or '').strip()
                    if request and img and img.startswith('/'):
                        img = request.build_absolute_uri(img)
                    title = (display.get('title_es') or display.get('title_en') or act.title_es or act.title_en or '').strip()
                    b['expanded'] = {
                        'id': str(act.id),
                        'slug': act.slug,
                        'title': title,
                        'image': img,
                        'duration_minutes': display.get('duration_minutes'),
                    }
            expanded_body.append(b)
        elif btype == 'embed_erasmus_activities':
            aids = b.get('erasmus_activity_ids') or []
            if not isinstance(aids, list):
                aids = []
            from apps.erasmus.models import ErasmusActivity
            from apps.erasmus.activity_display import get_activity_display_data
            acts = {
                str(act.id): act
                for act in ErasmusActivity.objects.filter(id__in=aids, is_active=True).select_related('experience')
            }
            b['expanded'] = []
            for aid in aids:
                if not aid:
                    continue
                act = acts.get(str(aid))
                if not act:
                    continue
                display = get_activity_display_data(act)
                img = (display.get('image') or '').strip()
                if request and img and img.startswith('/'):
                    img = request.build_absolute_uri(img)
                title = (display.get('title_es') or display.get('title_en') or act.title_es or act.title_en or '').strip()
                b['expanded'].append({
                    'id': str(act.id),
                    'slug': act.slug,
                    'title': title,
                    'image': img,
                    'duration_minutes': display.get('duration_minutes'),
                })
            expanded_body.append(b)
        elif btype == 'gallery':
            media_ids = b.get('media_ids') or []
            if isinstance(media_ids, list):
                b['images'] = [_asset_url(mid) for mid in media_ids if mid]
            expanded_body.append(b)
        elif btype == 'image':
            # Resolve media_asset_id to url if url not set
            if not b.get('url') and b.get('media_asset_id'):
                b['url'] = _asset_url(b.get('media_asset_id'))
            expanded_body.append(b)
        else:
            expanded_body.append(b)
    return expanded_body


class PublicTravelGuideListSerializer(serializers.ModelSerializer):
    """Public list: id, title, slug, excerpt, hero_image (first slide or single), destination, template, published_at."""

    hero_image = serializers.SerializerMethodField()
    destination_slug = serializers.CharField(source='destination.slug', read_only=True, allow_null=True)
    destination_name = serializers.CharField(source='destination.name', read_only=True, allow_null=True)

    class Meta:
        model = TravelGuide
        fields = [
            'id', 'title', 'slug', 'excerpt', 'hero_image',
            'destination_slug', 'destination_name', 'template', 'published_at',
        ]

    def get_hero_image(self, obj):
        slides = _resolve_hero_slides(obj, self.context.get('request'))
        if slides:
            return slides[0].get('image') or ''
        return _resolve_hero_url(obj, self.context.get('request'))


class PublicTravelGuideDetailSerializer(serializers.ModelSerializer):
    """Public detail: full guide with body blocks expanded (embed_* resolved). hero_slides for slider."""

    hero_image = serializers.SerializerMethodField()
    hero_slides = serializers.SerializerMethodField()
    destination_slug = serializers.CharField(source='destination.slug', read_only=True, allow_null=True)
    destination_name = serializers.CharField(source='destination.name', read_only=True, allow_null=True)
    body = serializers.SerializerMethodField()

    class Meta:
        model = TravelGuide
        fields = [
            'id', 'title', 'slug', 'excerpt', 'hero_image', 'hero_slides',
            'destination_slug', 'destination_name', 'template',
            'body', 'meta_title', 'meta_description', 'og_image',
            'published_at',
        ]

    def get_hero_image(self, obj):
        slides = _resolve_hero_slides(obj, self.context.get('request'))
        if slides:
            return slides[0].get('image') or ''
        return _resolve_hero_url(obj, self.context.get('request'))

    def get_hero_slides(self, obj):
        return _resolve_hero_slides(obj, self.context.get('request'))

    def get_body(self, obj):
        return _expand_embed_blocks(obj.body or [], self.context.get('request'), guide=obj)


class TravelGuideSerializer(serializers.ModelSerializer):
    """Superadmin CRUD: full model fields, body as-is (no expansion). Includes preview_token for vista previa."""

    class Meta:
        model = TravelGuide
        fields = [
            'id', 'destination', 'template', 'title', 'slug', 'excerpt',
            'hero_media_id', 'hero_image', 'hero_slides', 'body', 'status', 'published_at',
            'display_order', 'meta_title', 'meta_description', 'og_image',
            'preview_token', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'preview_token']


class TravelGuideListSerializer(serializers.ModelSerializer):
    """Superadmin list: compact fields + destination slug/name + preview_token for vista previa."""

    destination_slug = serializers.CharField(source='destination.slug', read_only=True, allow_null=True)
    destination_name = serializers.CharField(source='destination.name', read_only=True, allow_null=True)

    class Meta:
        model = TravelGuide
        fields = [
            'id', 'title', 'slug', 'destination_slug', 'destination_name',
            'template', 'status', 'published_at', 'display_order', 'created_at',
            'preview_token',
        ]
