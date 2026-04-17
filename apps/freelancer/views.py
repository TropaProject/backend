from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.conf import settings
from django.forms import model_to_dict
from django.db import models
from apps.freelancer.forms import FreelancerPointEditForm
from apps.routes.models import Point, PointEarning, FreelancerProfile, Mood, Interest, Tag, City, CityArea


# ---- Вспомогательные функции ----
def is_freelancer(user):
    return hasattr(user, 'freelancer_profile') and user.freelancer_profile.is_active


def is_editor(user):
    return user.is_staff or user.has_perm('points.can_review_points')  # permission создадим позже


def take_snapshot(point):
    """Сохраняет снимок редактируемых полей в JSON"""
    allowed_fields = [
        'description', 'keywords', 'average_visit_duration', 'average_cost',
        'best_visit_time', 'working_hours_json', 'is_seasonal', 'seasonal_months',
        'image_url', 'address'
    ]
    data = model_to_dict(point, fields=allowed_fields)
    # Для ManyToMany полей
    for m2m_field in ['tags', 'interests', 'moods']:
        data[m2m_field] = list(getattr(point, m2m_field).values_list('id', flat=True))
    return data


def restore_from_snapshot(point, snapshot):
    """Восстанавливает данные точки из снимка"""
    if not snapshot:
        return
    # Восстановление простых полей
    simple_fields = ['description', 'keywords', 'average_visit_duration', 'average_cost',
                     'best_visit_time', 'working_hours_json', 'is_seasonal', 'seasonal_months',
                     'image_url', 'address']
    for field in simple_fields:
        if field in snapshot:
            setattr(point, field, snapshot[field])
    # Восстановление ManyToMany
    for m2m_field in ['tags', 'interests', 'moods']:
        if m2m_field in snapshot:
            getattr(point, m2m_field).set(snapshot[m2m_field])
    point.save()


# ---- Фрилансерские view ----
@login_required
@user_passes_test(is_freelancer)
def freelancer_dashboard(request):
    profile = request.user.freelancer_profile
    assigned_points = Point.objects.filter(assigned_to=profile, edit_status__in=['assigned', 'rejected'])
    edited_points = Point.objects.filter(assigned_to=profile, edit_status='edited')
    approved_points = Point.objects.filter(assigned_to=profile, edit_status='approved')
    earnings = PointEarning.objects.filter(freelancer=profile)
    total_earned = profile.total_earned
    pending_earnings = earnings.filter(paid=False).aggregate(sum=models.Sum('amount'))['sum'] or 0

    context = {
        'assigned_points': assigned_points,
        'edited_points': edited_points,
        'approved_points': approved_points,
        'total_earned': total_earned,
        'pending_earnings': pending_earnings,
        'earnings': earnings[:10],
    }
    return render(request, 'dashboard.html', context)


@login_required
@user_passes_test(is_freelancer)
def edit_point(request, point_id):
    point = get_object_or_404(Point, id=point_id)
    profile = request.user.freelancer_profile
    if point.assigned_to != profile or point.edit_status not in ['assigned', 'rejected']:
        raise PermissionDenied("Вы не можете редактировать эту точку.")

    # Если статус rejected и пользователь нажал "исправить", то перед редактированием делаем новый снимок
    if point.edit_status == 'rejected' and request.method == 'GET':
        # При входе в форму для исправления – создаём свежий снимок
        point.snapshot_before_edit = take_snapshot(point)
        point.edit_status = 'assigned'
        point.review_comment = ''  # очищаем комментарий
        point.save()
        messages.info(request, "Точка переведена в статус 'назначена', вы можете исправить её.")
        return redirect('freelancer_edit_point', point_id=point.id)

    if request.method == 'POST':
        form = FreelancerPointEditForm(request.POST, instance=point)
        if form.is_valid():
            form.save()
            messages.success(request, "Изменения сохранены. Не забудьте отправить на проверку.")
            return redirect('freelancer_dashboard')
    else:
        form = FreelancerPointEditForm(instance=point)
    return render(request, 'edit_point.html', {'form': form, 'point': point})


@login_required
@user_passes_test(is_freelancer)
def submit_point(request, point_id):
    point = get_object_or_404(Point, id=point_id)
    profile = request.user.freelancer_profile
    if point.assigned_to != profile or point.edit_status != 'assigned':
        raise PermissionDenied()
    point.edit_status = 'edited'
    point.edited_at = timezone.now()
    point.save()
    messages.success(request, f"Точка '{point.name}' отправлена на проверку.")
    return redirect('freelancer_dashboard')


# ---- Административные view (редакторы) ----
from django.core.paginator import Paginator
from django.db.models import Q


@login_required
@user_passes_test(is_editor)
def assign_points(request):
    # Базовый queryset с сортировкой по id (убираем warning)
    points = Point.objects.filter(edit_status__in=['draft', 'rejected']) \
        .select_related('city', 'area') \
        .order_by('id')  # <-- добавляем order_by

    # Получаем параметры фильтрации
    area_id = request.GET.get('area')
    # Если нужно, можно сохранять в POST для массового выбора
    if request.method == 'POST':
        area_id = request.POST.get('area') or area_id

    # Применяем фильтр по району
    if area_id:
        points = points.filter(area_id=area_id)

    # Список районов, в которых есть точки со статусом draft/rejected (для выпадающего списка)
    # Используем values_list для получения ID районов
    area_ids = Point.objects.filter(edit_status__in=['draft', 'rejected']) \
        .values_list('area_id', flat=True).distinct()
    areas = CityArea.objects.filter(id__in=area_ids).select_related('city').order_by('city__name', 'name')

    # Список активных фрилансеров
    freelancers = FreelancerProfile.objects.filter(is_active=True)

    # Обработка POST (назначение)
    if request.method == 'POST':
        freelancer_id = request.POST.get('freelancer')
        select_all = request.POST.get('select_all') == 'true'

        if freelancer_id:
            freelancer = get_object_or_404(FreelancerProfile, id=freelancer_id)

            if select_all:
                points_to_assign = points  # уже отфильтрованный queryset
                count = points_to_assign.count()
                # Массовое обновление (более эффективно)
                points_to_assign.update(
                    assigned_to=freelancer,
                    edit_status='assigned',
                    assigned_at=timezone.now(),
                    review_comment=''
                )
                # Но нужно также сохранить snapshot для каждой точки
                # Поэтому используем итератор, как раньше
                for point in points_to_assign.iterator(chunk_size=500):
                    point.snapshot_before_edit = take_snapshot(point)
                    point.save(update_fields=['snapshot_before_edit', 'assigned_to', 'edit_status', 'assigned_at',
                                              'review_comment'])
                messages.success(request, f"Назначено {count} точек фрилансеру {freelancer.user.username}")
            else:
                point_ids = request.POST.getlist('points')
                if point_ids:
                    points_to_assign = Point.objects.filter(id__in=point_ids)
                    count = points_to_assign.count()
                    for point in points_to_assign:
                        point.snapshot_before_edit = take_snapshot(point)
                        point.assigned_to = freelancer
                        point.edit_status = 'assigned'
                        point.assigned_at = timezone.now()
                        point.review_comment = ''
                        point.save()
                    messages.success(request, f"Назначено {count} точек фрилансеру {freelancer.user.username}")

            # Редирект с сохранением фильтра по району
            redirect_url = request.path
            if area_id:
                redirect_url += f"?area={area_id}"
            return redirect(redirect_url)
        else:
            messages.error(request, "Выберите фрилансера")

    # Пагинация (теперь предупреждения не будет)
    paginator = Paginator(points, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'points': page_obj,
        'freelancers': freelancers,
        'areas': areas,
        'selected_area': int(area_id) if area_id else '',
        'total_count': points.count(),
        'filter_params': {
            'area': area_id or '',
        }
    }
    return render(request, 'assign_points.html', context)


from django.core.paginator import Paginator
from django.db.models import Q
from datetime import datetime


@login_required
@user_passes_test(is_editor)
def review_points(request):
    # Базовый queryset
    points = Point.objects.filter(edit_status='edited').select_related('city', 'assigned_to__user').order_by(
        '-edited_at')

    # Параметры фильтрации из GET
    freelancer_id = request.GET.get('freelancer')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if freelancer_id:
        points = points.filter(assigned_to_id=freelancer_id)
    if date_from:
        try:
            date_from_parsed = datetime.strptime(date_from, '%Y-%m-%d')
            points = points.filter(edited_at__date__gte=date_from_parsed)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_parsed = datetime.strptime(date_to, '%Y-%m-%d')
            points = points.filter(edited_at__date__lte=date_to_parsed)
        except ValueError:
            pass

    # Список фрилансеров, у которых есть точки на проверке
    freelancers = FreelancerProfile.objects.filter(point__edit_status='edited').distinct()

    # Обработка массовых действий
    if request.method == 'POST':
        action = request.POST.get('action')
        point_ids = request.POST.getlist('selected_points')
        if point_ids and action in ['approve_selected', 'reject_selected']:
            comment = request.POST.get('comment', '')
            points_selected = Point.objects.filter(id__in=point_ids)
            count = points_selected.count()
            for point in points_selected:
                if action == 'approve_selected':
                    # Одобрить
                    point.edit_status = 'approved'
                    point.reviewed_by = request.user
                    point.snapshot_before_edit = None
                    point.save()
                    # Начисление оплаты
                    amount = getattr(settings, 'FREELANCER_PAYMENT_PER_POINT', 100)
                    earning = PointEarning.objects.create(
                        point=point,
                        freelancer=point.assigned_to,
                        amount=amount
                    )
                    point.assigned_to.total_earned += amount
                    point.assigned_to.save()
                else:  # reject_selected
                    # Восстановить из снимка
                    restore_from_snapshot(point, point.snapshot_before_edit)
                    point.edit_status = 'rejected'
                    point.reviewed_by = request.user
                    point.review_comment = comment
                    point.snapshot_before_edit = None
                    point.save()
            messages.success(request, f"Обработано {count} точек.")
            return redirect('review_points')

    # Пагинация
    paginator = Paginator(points, 20)  # 20 точек на страницу
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'points': page_obj,
        'freelancers': freelancers,
        'selected_freelancer': int(freelancer_id) if freelancer_id else '',
        'date_from': date_from or '',
        'date_to': date_to or '',
        'total_count': points.count(),
    }
    return render(request, 'review_points.html', context)

@login_required
@user_passes_test(is_editor)
def compare_point(request, point_id):
    point = get_object_or_404(Point, id=point_id, edit_status='edited')
    snapshot = point.snapshot_before_edit
    # Текущие данные (то, что предложил фрилансер)
    current_data = {
        'description': point.description,
        'keywords': point.keywords,
        'average_visit_duration': point.average_visit_duration,
        'average_cost': point.average_cost,
        'best_visit_time': ', '.join(point.best_visit_time) if point.best_visit_time else '',
        'working_hours_json': point.working_hours_json,
        'is_seasonal': point.is_seasonal,
        'seasonal_months': point.seasonal_months,
        'image_url': point.image_url,
        'address': point.address,
        'tags': ', '.join([tag.name for tag in point.tags.all()]),
        'interests': ', '.join([i.id for i in point.interests.all()]),
        'moods': ', '.join([m.id for m in point.moods.all()]),
    }
    # Данные из снимка (было)
    original_data = {}
    if snapshot:
        original_data = {
            'description': snapshot.get('description', ''),
            'keywords': snapshot.get('keywords', []),
            'average_visit_duration': snapshot.get('average_visit_duration', ''),
            'average_cost': snapshot.get('average_cost', ''),
            'best_visit_time': snapshot.get('best_visit_time', []),
            'working_hours_json': snapshot.get('working_hours_json', ''),
            'is_seasonal': snapshot.get('is_seasonal', False),
            'seasonal_months': snapshot.get('seasonal_months', []),
            'image_url': snapshot.get('image_url', ''),
            'address': snapshot.get('address', ''),
            'tags': ', '.join([Tag.objects.get(id=tid).name for tid in snapshot.get('tags', [])]),
            'interests': ', '.join([Interest.objects.get(id=iid).id for iid in snapshot.get('interests', [])]),
            'moods': ', '.join([Mood.objects.get(id=mid).id for mid in snapshot.get('moods', [])]),
        }
    else:
        original_data = {k: '(нет данных)' for k in current_data}

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            # Одобрить: очищаем снимок, меняем статус, начисляем оплату
            point.edit_status = 'approved'
            point.reviewed_by = request.user
            point.snapshot_before_edit = None
            point.save()
            # Начисление
            amount = getattr(settings, 'FREELANCER_PAYMENT_PER_POINT', 100)
            earning = PointEarning.objects.create(
                point=point,
                freelancer=point.assigned_to,
                amount=amount
            )
            point.assigned_to.total_earned += amount
            point.assigned_to.save()
            messages.success(request, f"Точка '{point.name}' одобрена, фрилансеру начислено {amount} руб.")
            return redirect('review_points')
        elif action == 'reject':
            comment = request.POST.get('comment', '')
            # Восстановить из снимка
            restore_from_snapshot(point, point.snapshot_before_edit)
            point.edit_status = 'rejected'
            point.reviewed_by = request.user
            point.review_comment = comment
            point.snapshot_before_edit = None
            point.save()
            messages.warning(request, f"Точка '{point.name}' отклонена. Комментарий: {comment}")
            return redirect('review_points')
    return render(request, 'compare_point.html',
                  {'point': point, 'original': original_data, 'current': current_data})


from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_protect
from django.contrib import messages


@csrf_protect
def custom_login(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'freelancer_profile'):
            return redirect('freelancer_dashboard')
        elif request.user.is_staff:
            return redirect('assign_points')
        return redirect('/')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            # После входа перенаправляем в зависимости от роли
            if hasattr(user, 'freelancer_profile'):
                return redirect('freelancer_dashboard')
            elif user.is_staff:
                return redirect('assign_points')
            return redirect('/')
        else:
            error = 'Неверное имя пользователя или пароль'

    return render(request, 'login.html', {'error': error})