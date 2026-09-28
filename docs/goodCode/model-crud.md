# 模型自带增删改查

## 要解决的变化点

每张表都要创建、读取、更新和删除。这些步骤如果写在各自的 SQL 里，新增一张表就要再写一套语句。

## 使用的设计

模型基类。子类只声明表名和列，增删改查由 `CrudModel` 实现。

## 关键类

- `backend/app/db/crud_model.py` 中的 `CrudModel`
- `backend/app/users/user_model.py` 中的 `User`

## 以后怎么扩展

新增一张表时，继承 `CrudModel` 并声明列。调用 `create`、`get`、`update`、`delete`。不要再为这张表写仓库，也不要写 `INSERT` 或 `SELECT`。
