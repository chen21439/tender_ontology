```cypher
CREATE (d:DocumentSystem {
  文档路径: '/深圳市交易集团/深圳理工大学2025年图书馆家具采购项目'
});

MATCH (d:DocumentSystem {`文档路径`: '/深圳市交易集团/深圳理工大学2025年图书馆家具采购项目'})
CREATE (b:包号 {name: '第1包'})
CREATE (d)-[:HAS_FIELD]->(b);

```