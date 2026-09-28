# 模型自带增删改查

## 要解决的变化点

每张表都要创建、读取、更新和删除。这些步骤如果写在各个仓库的 SQL 里，新增一张表就要再写一套语句。

## 使用的设计

模型基类。子类只声明表名和列，增删改查由 `CrudModel` 实现。

## 关键类

- `backend/app/db/crud_model.py` 中的 `CrudModel`
- `backend/app/users/user_model.py` 中的 `User`
- `backend/app/users/mysql_user_repository.py` 只调用模型方法，并转换成用户模块自己的结果

## 以后怎么扩展

新增一张表时，继承 `CrudModel` 并声明列。不要在仓库里写 `INSERT` 或 `SELECT`。调用方仍然依赖自己的仓库接口，不直接持有数据库会话。
