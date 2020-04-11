from django.shortcuts import render, redirect
from django.views.generic import View
from django.core.cache import cache
from django.urls import reverse
from django.core.paginator import Paginator
from django.views.generic import ListView

from goods.models import *
from order.models import *
from django_redis import get_redis_connection
from utils.mixin import LoginRequiredMixin


# Create your views here.


class IndexView(View):
    """首页视图"""

    def get(self, request):
        """获取首页"""
        # 尝试从缓存中获取数据
        context = cache.get('index_page_data')
        if context is None:
            # 缓存中没有数据
            # print('设置缓存')

            # 获取分类展示商品
            types = GoodsType.objects.all()

            # 获取轮播图
            goods_banners = IndexGoodsBanner.objects.all().order_by('index')

            # 获取促销活动
            promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

            # 获取商品分类
            type_goods = IndexTypeGoodsBanner.objects.all()
            for type in types:
                title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0)
                image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1)
                # 给type增加属性
                type.title_banners = title_banners
                type.image_banners = image_banners

            context = {
                'types': types,
                'goods_banners': goods_banners,
                'promotion_banners': promotion_banners
            }

            # 设置缓存,首页数据缓存
            # 参数：key value timeout
            cache.set('index_page_data', context, 3600)

        # 获取用户购物车中商品的数目，用户不登录时不能访问购物车数目
        user = request.user
        cart_count = 0
        if user.is_authenticated:
            # 用户已登录
            con = get_redis_connection('default')
            cart_key = 'cart_' + str(user.id)
            cart_count = con.hlen(cart_key)

        # update()方法，如果key存在就是更新，不存在就是新增
        context.update(cart_count=cart_count)

        return render(request, 'goods/index.html', context=context)


# /goods/商品id
class DetailView(View):
    """商品详情页"""
    def get(self, request, goods_id):
        """显示详情页"""
        try:
            sku = GoodsSKU.objects.get(id=goods_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在，返回首页
            return redirect(reverse('goods:index'))

        # 获取商品种类信息
        types = GoodsType.objects.all()
        # 获取商品的评论信息
        sku_orders = OrderGoods.objects.filter(sku=sku).exclude(comment='')
        # 获取新品信息
        new_skus = GoodsSKU.objects.filter(type=sku.type).order_by('-create_time')[:2]

        same_sku_spu = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=goods_id)

        # 获取用户购物车中商品的数目，用户不登录时不能访问购物车数目
        user = request.user
        cart_count = 0
        if user.is_authenticated:
            # 用户已登录
            con = get_redis_connection('default')
            cart_key = 'cart_' + str(user.id)
            cart_count = con.hlen(cart_key)

            # 获取用户浏览记录
            con = get_redis_connection('default')
            history_key = 'history_' + str(user.id)
            # 移除商品信息，如果商品id不在，则不会做任何操作
            con.lrem(history_key, 0, goods_id)
            # 在列表的左侧插入id
            con.lpush(history_key, goods_id)
            # 只保留列表的五个数据
            con.ltrim(history_key, 0, 4)

        context = {
            'sku': sku, 'types': types,
            'sku_orders': sku_orders,
            'new_skus': new_skus,
            'cart_count': cart_count,
            'same_sku_spu': same_sku_spu
        }

        return render(request, 'goods/detail.html', context=context)


# /goods/1/1?sort=
# 种类id, 页码, 排序方式
# resful api --> 请求一种资源
# /list?type_id=种类id&page=页码&sort=排序方式
# /list/种类id/页码/排序方式
# /list/种类id/页码?sort=排序方式（使用这种方式，遵循resful api风格）
class ListView(View):
    """列表页"""
    def get(self, request, type_id, page):
        """显示列表页"""
        try:
            type = GoodsType.objects.get(id=type_id)
        except GoodsType.DoesNotExist:
            # 种类不存在
            return redirect(reverse('goods:index'))
        # 获取商品的分类信息
        types = GoodsType.objects.all()

        # 获取排序的方式
        # sort=default 按照默认id排序, sort=price 按照商品价格排序, sort=hot 按照商品的销量排序
        sort = request.GET.get('sort')
        # 获取分类商品的信息
        sort_type = ""
        if sort == 'price':
            sort_type = 'price'
        elif sort == 'hot':
            sort_type = '-sales'
        else:
            sort = 'default'
            sort_type = '-id'
        skus = GoodsSKU.objects.filter(type=type).order_by(sort_type)

        # 对数据进行分页
        paginator = Paginator(skus, 1)

        # 获取第page页的内容
        try:
            page = int(page)
        except ValueError:
            page = 1

        # 如果page大于总页数
        if page > paginator.num_pages:
            page = paginator.num_pages
        if page < 0:
            page = 1
        # 获取page页的Page的实例对象
        skus_page = paginator.page(page)

        # todo: 进行页码的控制，页面上最多显示5个页码
        # 1.总页数小于5页，页面上显示所有页码
        # 2.如果当前页是前3页，显示1-5页
        # 3.如果当前页是后3页，显示后5页
        # 4.其他情况，显示当前页的前两页，当前页，后两页
        pages = ""
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages+1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(pages -2 , pages + 3)

        # 获取新品信息
        new_skus = GoodsSKU.objects.filter(type=type).order_by('-create_time')[:2]

        # 获取购物车数量
        user = request.user
        cart_count = 0
        if user.is_authenticated:
            con = get_redis_connection('default')
            cart_key = 'cart_' + str(user.id)
            cart_count = con.hlen(cart_key)

        # 组织模板上下文
        context = {"types": types, "skus_page": skus_page,
                   "new_skus": new_skus, "cart_count": cart_count,
                   "type": type, "sort": sort, "pages": pages,
        }
        # 使用模板
        return render(request, "goods/list.html", context=context)


# url: comment/order_id
class CommentView(LoginRequiredMixin, View):
    """订单评价"""
    def get(self, request, order_id):
        """提供评论页面"""
        user = request.user

        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse('user:order'))

        # 业务逻辑
        # 获取订单商品的信息
        order_skus = OrderGoods.objects.filter(order_id=order_id)
        for order_sku in order_skus:
            # 计算商品的小计
            amount = order_sku.count * order_sku.price
            order_sku.amount = amount
        order.order_skus = order_skus
        # 返回应答
        return render(request, "order/order_comment.html", {'order': order})

    def post(self, request, order_id):
        """处理评论内容"""
        user = request.user
        # 校验数据
        if not order_id:
            print("111")
            return redirect(reverse('user:order'))
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            print("112")
            return redirect(reverse('user:order'))

        # 获取评论条数
        total_count = request.POST.get('total_count')
        total_count = int(total_count)

        # 循环获取订单中商品的评论内容
        for i in range(1, total_count + 1):
            # 获取评论商品的id
            sku_id = request.POST.get("sku_%d" % i)  # sku_1 sku_2 sku_3
            # 获取评论的商品的内容
            content = request.POST.get('content_%d' % i, '')  # content_1 content_2
            try:
                order_goods = OrderGoods.objects.get(order=order, sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                continue

            order_goods.comment = content
            order_goods.save()

        order.order_status = 5      # 已完成
        order.save()
        print("113")
        # return redirect(reverse('user:order', kwargs={'page': 1}))
        return redirect(reverse('user:order'))



















