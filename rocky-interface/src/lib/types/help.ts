export type ApiFaqItem = Partial<{
	question: string;
	answer: string;
}>;

export type HelpResource = {
	label: string;
	description: string;
	action: string;
	href: string;
	isInternalRoute: boolean;
};

export type HelpDocumentStatus = 'New' | 'Updated' | 'Current';

export type HelpDocument = {
	title: string;
	category: string;
	date: string;
	status: HelpDocumentStatus;
	url: string;
};

export type FaqItem = {
	question: string;
	answer: string;
};

export function normalizeFaqItem(raw: ApiFaqItem): FaqItem {
	return {
		question: raw.question?.trim() || 'Question unavailable',
		answer: raw.answer?.trim() || 'Answer unavailable'
	};
}

export function normalizeFaqItems(rawItems: ApiFaqItem[]): FaqItem[] {
	return rawItems.map(normalizeFaqItem);
}
