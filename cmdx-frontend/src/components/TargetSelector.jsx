function TargetSelector({
  factories,
  parts,
  products,
  selectedFactory,
  selectedPart,
  selectedProduct,
  targetType,
  onFactoryChange,
  onPartChange,
  onProductChange,
  onTargetTypeChange,
}) {
  return (
    <div className="select-area">
      <select value={selectedFactory} onChange={(e) => onFactoryChange(e.target.value)}>
        {factories.map((factory) => (
          <option key={factory.factory_id} value={factory.factory_id}>
            {factory.factory_id} {factory.factory_name}
          </option>
        ))}
      </select>
      <div className="segmented">
        <button className={targetType === "part" ? "active" : ""} onClick={() => onTargetTypeChange("part")}>
          部品
        </button>
        <button className={targetType === "product" ? "active" : ""} onClick={() => onTargetTypeChange("product")}>
          製品アセンブリ
        </button>
      </div>
      {targetType === "part" ? (
        <select value={selectedPart} onChange={(e) => onPartChange(e.target.value)}>
          {parts.map((part) => (
            <option key={part.parts_id} value={part.parts_id}>
              {part.parts_id} {part.parts_name}
            </option>
          ))}
        </select>
      ) : (
        <select value={selectedProduct} onChange={(e) => onProductChange(e.target.value)}>
          {products.map((product) => (
            <option key={product.product_id} value={product.product_id}>
              {product.product_id} {product.product_name}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

export default TargetSelector;
